from __future__ import annotations

import asyncio
import hashlib
import json
import os
from uuid import uuid4
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .adapters import get_adapter_snapshot, list_adapter_snapshots
from .domain import detect_berth_conflicts, score_port_call
from .observability import metrics, observe_http
from .models import (
    AdapterHealth, DataDomain, DataSourceMode, DataSourceProvenance,
    IncidentStatus, IncidentType, IntegrationIdentity, LinkMode, OperationsEvent,
    OperatorIdentity, RiskLevel, ScenarioRunEvidence, ServiceDurationCalibration,
    ServiceKind, VesselCoordinationSnapshot, VesselRuntimeEvent,
    VesselOperationalException, VesselRuntimeEventReceipt, VesselRuntimeEventRecord, VesselRuntimeEventType,
)
from .simulator import HarborSimulator, RecoveryProposalStaleError
from .security import (
    configured_approvers,
    configured_integrations,
    current_integration,
    current_operator,
    recovery_approver,
)
from .scenarios import get_scenario, list_scenarios
from .storage import OperationsStore


store = OperationsStore()
sim = HarborSimulator()
_runtime_ready = False
_schema_mode = "uninitialized"


def build_simulator() -> HarborSimulator:
    snapshot = store.load_snapshot()
    evidence_batches = store.list_recovery_proposal_evidence(limit=200)
    proposal_history = [
        proposal
        for batch in reversed(evidence_batches)
        for proposal in batch.proposals
    ]
    return HarborSimulator(
        initial=snapshot,
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
        recovery_proposal_evidence_sink=store.save_recovery_proposal_evidence,
        proposal_history=proposal_history,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global sim, _runtime_ready, _schema_mode

    configured_approvers()
    configured_integrations()
    _schema_mode = os.getenv("PORTFLOW_SCHEMA_MODE", "migrate").strip().lower()
    if _schema_mode == "migrate":
        store.migrate_schema()
    elif _schema_mode == "verify":
        store.verify_schema()
    else:
        raise RuntimeError(
            "PORTFLOW_SCHEMA_MODE must be either 'migrate' or 'verify'"
        )

    sim = build_simulator()
    _runtime_ready = True
    stop = asyncio.Event()

    async def runner():
        while not stop.is_set():
            sim.tick()
            await asyncio.sleep(2)

    task = asyncio.create_task(runner())
    try:
        yield
    finally:
        _runtime_ready = False
        stop.set()
        task.cancel()


app = FastAPI(title="KRATIA Shore", version=__version__, lifespan=lifespan)
app.middleware("http")(observe_http)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectivityRequest(BaseModel):
    mode: LinkMode


class IncidentRequest(BaseModel):
    incident_type: IncidentType
    target_port_call_id: str | None = None
    target_resource_id: str | None = None
    impact_minutes: int | None = Field(default=None, ge=0, le=720)


class ServiceDurationCalibrationRequest(BaseModel):
    service_kind: ServiceKind
    duration_minutes: int = Field(ge=1, le=24 * 60)
    source_id: str = Field(min_length=1, max_length=120)
    mode: DataSourceMode
    provider: str = Field(min_length=1, max_length=200)
    observed_at: datetime
    stale_after_seconds: int = Field(default=2_592_000, ge=60, le=31_536_000)
    detail: str | None = Field(default=None, max_length=500)


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "service": "portflow-api",
        "version": __version__,
    }


@app.get("/readyz")
def readyz():
    schema = store.schema_status()
    authorization_configured = bool(configured_approvers())
    integration_authorization_configured = bool(configured_integrations())
    ready = (
        _runtime_ready
        and bool(schema["database_reachable"])
        and bool(schema["compatible"])
    )
    payload = {
        "ok": ready,
        "service": "portflow-api",
        "version": __version__,
        "runtime_ready": _runtime_ready,
        "schema_mode": _schema_mode,
        "schema": schema,
        "authorization_configured": authorization_configured,
        "integration_authorization_configured": (
            integration_authorization_configured
        ),
    }
    if not ready:
        raise HTTPException(status_code=503, detail=payload)
    return payload


def public_portfolio_mode() -> bool:
    return os.getenv("PORTFLOW_PUBLIC_MODE", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


@app.get("/metrics")
def prometheus_metrics():
    if public_portfolio_mode():
        raise HTTPException(status_code=404, detail="Not found")
    schema = store.schema_status()
    harbor_metrics = sim.overview().metrics if _runtime_ready else None
    return Response(
        content=metrics.render(
            runtime_ready=_runtime_ready,
            schema_compatible=bool(schema["compatible"]),
            authorization_configured=bool(configured_approvers()),
            harbor_metrics=harbor_metrics,
        ),
        media_type="text/plain; version=0.0.4",
    )


@app.get("/api/v1/auth/me")
def auth_me(identity: OperatorIdentity = Depends(current_operator)):
    return identity


def _require_integration_vessel(
    identity: IntegrationIdentity,
    vessel_id: str,
) -> None:
    if vessel_id not in identity.vessel_ids:
        raise HTTPException(
            status_code=403,
            detail="Integration is not authorized for this vessel",
        )


@app.get("/api/v1/integration/contracts")
def integration_contracts():
    return {
        "event_contract": "portflow.vessel-event.v1",
        "event_receipt_contract": "portflow.vessel-event-receipt.v1",
        "coordination_contract": "portflow.coordination.v1",
        "event_types": [item.value for item in VesselRuntimeEventType],
        "transports": {
            "http_ingest": "POST /api/v1/integration/vessel-events",
            "http_coordination": (
                "GET /api/v1/integration/port-calls/{call_id}/coordination"
            ),
            "kafka": (
                "Reserved for a future transport binding using the same "
                "portflow.vessel-event.v1 envelope."
            ),
        },
        "invariants": {
            "raw_sensor_streams_owned_by_vessel_runtime": True,
            "portflow_accepts_normalized_events_only": True,
            "coordination_is_advisory_only": True,
            "human_approval_required_for_recovery": True,
            "direct_actuation_allowed": False,
            "event_id_is_idempotency_key": True,
        },
        "schemas": {
            "vessel_event": VesselRuntimeEvent.model_json_schema(),
            "coordination": VesselCoordinationSnapshot.model_json_schema(),
        },
    }


@app.post(
    "/api/v1/integration/vessel-events",
    response_model=VesselRuntimeEventReceipt,
)
def ingest_vessel_runtime_event(
    event: VesselRuntimeEvent,
    identity: IntegrationIdentity = Depends(current_integration),
):
    _require_integration_vessel(identity, event.vessel_id)

    if not any(vessel.id == event.vessel_id for vessel in sim.vessels):
        raise HTTPException(status_code=404, detail="Unknown vessel")

    if event.port_call_id is not None:
        call = next(
            (
                item for item in sim.port_calls
                if item.id == event.port_call_id
            ),
            None,
        )
        if call is None:
            raise HTTPException(status_code=404, detail="Unknown port call")
        if call.vessel_id != event.vessel_id:
            raise HTTPException(
                status_code=409,
                detail="Port call does not belong to the event vessel",
            )

    encoded = event.model_dump_json().encode("utf-8")
    if len(encoded) > 65_536:
        raise HTTPException(
            status_code=413,
            detail="Normalized vessel event exceeds 64 KiB contract limit",
        )

    existing = store.get_vessel_runtime_event(event.event_id)
    if existing is not None:
        if (
            existing.integration_id != identity.integration_id
            or existing.event != event
        ):
            raise HTTPException(
                status_code=409,
                detail="event_id already exists with different content",
            )
        return VesselRuntimeEventReceipt(
            event_id=event.event_id,
            accepted_at=existing.received_at,
            duplicate=True,
        )

    received_at = datetime.now(timezone.utc).replace(microsecond=0)
    record = VesselRuntimeEventRecord(
        event=event,
        integration_id=identity.integration_id,
        received_at=received_at,
    )
    stored = store.save_vessel_runtime_event(record)
    if not stored:
        existing = store.get_vessel_runtime_event(event.event_id)
        if (
            existing is None
            or existing.integration_id != identity.integration_id
            or existing.event != event
        ):
            raise HTTPException(
                status_code=409,
                detail="event_id was concurrently claimed with different content",
            )
        return VesselRuntimeEventReceipt(
            event_id=event.event_id,
            accepted_at=existing.received_at,
            duplicate=True,
        )

    store.append_event(
        OperationsEvent(
            id=f"vessel-runtime-{event.event_id}",
            occurred_at=received_at,
            category="vessel_runtime",
            severity=RiskLevel.LOW,
            title=f"Vessel runtime event: {event.event_type.value}",
            message=(
                f"Accepted normalized {event.event_type.value} event "
                f"{event.event_id} from integration {identity.integration_id}; "
                f"sequence {event.sequence}."
            ),
            vessel_id=event.vessel_id,
            port_call_id=event.port_call_id,
            source_id=identity.integration_id,
        )
    )
    metrics.inc("portflow_vessel_events_total")

    return VesselRuntimeEventReceipt(
        event_id=event.event_id,
        accepted_at=received_at,
        duplicate=False,
    )


@app.get("/api/v1/integration/vessel-events")
def vessel_runtime_events(
    limit: int = 100,
    vessel_id: str | None = None,
    identity: IntegrationIdentity = Depends(current_integration),
):
    if vessel_id is not None:
        _require_integration_vessel(identity, vessel_id)

    rows = store.list_vessel_runtime_events(
        limit=limit,
        integration_id=identity.integration_id,
        vessel_id=vessel_id,
    )
    allowed = set(identity.vessel_ids)
    rows = [row for row in rows if row.event.vessel_id in allowed]
    return {"count": len(rows), "events": rows}


_CREW_EXCEPTION_EVENT_STATE = {
    "crew.exception.opened": "open",
    "crew.attention.acknowledged": "acknowledged",
    "crew.attention.claimed": "claimed",
    "crew.attention.escalated": "escalated",
    "crew.attention.released": "released",
    "crew.exception.override_recorded": "override_recorded",
    "crew.attention.resolved": "resolved",
}

_MAX_CREW_EXCEPTION_LIFECYCLE_EVENTS = 64


_CREW_EXCEPTION_RISK = {
    "open": RiskLevel.MEDIUM,
    "acknowledged": RiskLevel.LOW,
    "claimed": RiskLevel.LOW,
    "escalated": RiskLevel.MEDIUM,
    "released": RiskLevel.MEDIUM,
    "override_recorded": RiskLevel.LOW,
    "resolved": RiskLevel.LOW,
}


def _crew_exception_copy(state: str) -> tuple[str, str]:
    if state == "open":
        return (
            "Crew operational exception requires review",
            (
                "Vessel runtime opened a local advisory operational exception. "
                "Private supporting evidence remains onboard."
            ),
        )
    if state == "acknowledged":
        return (
            "Crew operational exception acknowledged",
            "A vessel supervisor acknowledged the local advisory exception.",
        )
    if state == "claimed":
        return (
            "Crew operational exception under review",
            (
                "A vessel supervisor claimed local review ownership. "
                "Private review context remains onboard."
            ),
        )
    if state == "escalated":
        return (
            "Crew operational exception escalated",
            "Local review was escalated onboard.",
        )
    if state == "released":
        return (
            "Crew operational exception released",
            "Local review ownership was released onboard.",
        )
    if state == "override_recorded":
        return (
            "Crew operational override recorded",
            (
                "A reason-bound local override decision was recorded. "
                "Private rationale remains onboard."
            ),
        )
    return (
        "Crew operational exception resolved",
        "The vessel supervisor resolved the local advisory exception.",
    )


def _crew_exception_lifecycle_valid(
    lifecycle: list[VesselOperationalException],
) -> bool:
    if not lifecycle or lifecycle[0].state != "open":
        return False

    allowed_next = {
        "open": {"acknowledged"},
        "acknowledged": {"claimed"},
        "claimed": {
            "escalated",
            "released",
            "override_recorded",
            "resolved",
        },
        "escalated": {
            "escalated",
            "released",
            "override_recorded",
            "resolved",
        },
        "override_recorded": {
            "escalated",
            "released",
            "resolved",
        },
        "released": {"claimed"},
        "resolved": set(),
    }
    override_seen = False
    current = "open"
    for item in lifecycle[1:]:
        next_state = item.state
        if next_state not in allowed_next[current]:
            return False
        if next_state == "override_recorded":
            if override_seen:
                return False
            override_seen = True
        current = next_state
    return True


def _project_vessel_operational_exception(
    record: VesselRuntimeEventRecord,
) -> VesselOperationalException | None:
    event = record.event
    if event.event_type is not VesselRuntimeEventType.CONSTRAINT:
        return None

    payload = event.payload
    if payload.get("category") != "crew_operational_exception":
        return None
    if payload.get("privacy_minimized") is not True:
        return None
    if payload.get("advisory_only") is not True:
        return None
    if payload.get("execution_authorized") is not False:
        return None
    if event.evidence_refs:
        # Crew-exception evidence is vessel-private in the v0.0.78 contract.
        return None

    runtime_event_type = str(
        payload.get("runtime_event_type") or ""
    )
    expected_state = _CREW_EXCEPTION_EVENT_STATE.get(
        runtime_event_type
    )
    state = str(payload.get("state") or "")
    if expected_state is None or state != expected_state:
        return None

    exception_ref = str(payload.get("exception_ref") or "")
    if (
        not exception_ref.startswith("mrt-exception-")
        or len(exception_ref) != 34
        or any(
            character not in "0123456789abcdef"
            for character in exception_ref.removeprefix(
                "mrt-exception-"
            )
        )
    ):
        return None

    title, summary = _crew_exception_copy(state)
    return VesselOperationalException(
        vessel_id=event.vessel_id,
        port_call_id=event.port_call_id,
        exception_ref=exception_ref,
        state=state,
        risk=_CREW_EXCEPTION_RISK[state],
        title=title,
        summary=summary,
        first_source_sequence=event.sequence,
        latest_source_sequence=event.sequence,
        opened_at=event.occurred_at,
        updated_at=event.occurred_at,
        opened_event_id=event.event_id,
        latest_event_id=event.event_id,
        lifecycle_event_count=1,
        history=[
            {
                "state": state,
                "source_sequence": event.sequence,
                "occurred_at": event.occurred_at,
            }
        ],
        privacy_minimized=True,
        advisory_only=True,
        execution_authorized=False,
    )


@app.get("/api/v1/operations/vessel-exceptions")
def operator_vessel_exceptions(
    limit: int = Query(default=100, ge=1, le=500),
    vessel_id: str | None = Query(default=None, max_length=80),
    identity: OperatorIdentity = Depends(current_operator),
):
    del identity  # Authorization is the boundary; this endpoint is read-only.
    rows = store.list_vessel_runtime_events(
        limit=1000,
        vessel_id=vessel_id,
    )
    lifecycle_by_key: dict[
        tuple[str, str],
        list[tuple[str, VesselOperationalException]],
    ] = {}
    for record in rows:
        item = _project_vessel_operational_exception(record)
        if item is None:
            continue
        lifecycle_by_key.setdefault(
            (item.vessel_id, item.exception_ref),
            [],
        ).append((record.integration_id, item))

    projected: list[VesselOperationalException] = []
    for (vessel_id, exception_ref), scoped_lifecycle in lifecycle_by_key.items():
        integration_ids = {
            integration_id
            for integration_id, _ in scoped_lifecycle
        }
        if len(integration_ids) != 1:
            # One opaque exception lifecycle must have exactly one machine
            # integration authority inside a vessel scope. Conflicting
            # producers fail closed instead of being merged or duplicated.
            continue
        lifecycle = [
            item
            for _, item in scoped_lifecycle
        ]
        if len(lifecycle) > _MAX_CREW_EXCEPTION_LIFECYCLE_EVENTS:
            continue
        ordered = sorted(
            lifecycle,
            key=lambda item: (
                item.latest_source_sequence,
                item.updated_at,
                item.latest_event_id,
            ),
        )
        opening = ordered[0]

        # One monotonically ordered, privacy-safe lifecycle per opaque ref.
        # Impossible transitions and state after terminal resolution fail closed.
        if any(
            current.latest_source_sequence
            <= previous.latest_source_sequence
            for previous, current in zip(
                ordered,
                ordered[1:],
            )
        ):
            continue
        if not _crew_exception_lifecycle_valid(ordered):
            continue

        latest = ordered[-1]
        title, summary = _crew_exception_copy(
            latest.state
        )
        projected.append(
            VesselOperationalException(
                vessel_id=vessel_id,
                port_call_id=latest.port_call_id,
                exception_ref=exception_ref,
                state=latest.state,
                risk=_CREW_EXCEPTION_RISK[
                    latest.state
                ],
                title=title,
                summary=summary,
                first_source_sequence=(
                    opening.first_source_sequence
                ),
                latest_source_sequence=(
                    latest.latest_source_sequence
                ),
                opened_at=opening.opened_at,
                updated_at=latest.updated_at,
                opened_event_id=opening.opened_event_id,
                latest_event_id=latest.latest_event_id,
                lifecycle_event_count=len(ordered),
                history=[
                    history_item
                    for item in ordered
                    for history_item in item.history
                ],
                privacy_minimized=True,
                advisory_only=True,
                execution_authorized=False,
            )
        )

    projected = sorted(
        projected,
        key=lambda item: (
            item.updated_at,
            item.latest_source_sequence,
            item.exception_ref,
        ),
        reverse=True,
    )[:limit]
    return {
        "count": len(projected),
        "exceptions": projected,
        "execution_authorized": False,
    }


@app.get(
    "/api/v1/integration/port-calls/{call_id}/coordination",
    response_model=VesselCoordinationSnapshot,
)
def vessel_coordination(
    call_id: str,
    identity: IntegrationIdentity = Depends(current_integration),
):
    call = next((item for item in sim.port_calls if item.id == call_id), None)
    if call is None:
        raise HTTPException(status_code=404, detail="Unknown port call")

    _require_integration_vessel(identity, call.vessel_id)

    active_incidents = [
        incident
        for incident in sim.incidents
        if (
            incident.status == IncidentStatus.ACTIVE
            and incident.target_port_call_id in {None, call.id}
        )
    ]
    proposals = sim.generate_recovery_proposals(
        call_id=call.id,
        evidence_trigger="integration_coordination",
    )

    return VesselCoordinationSnapshot(
        generated_at=datetime.now(timezone.utc).replace(microsecond=0),
        port_call_id=call.id,
        vessel_id=call.vessel_id,
        berth_id=call.berth_id,
        arrival_eta=call.arrival_eta,
        departure_eta=call.departure_eta,
        delay_minutes=call.delay_minutes,
        risk=call.risk,
        stages=call.stages,
        service_steps=[
            step for step in sim.service_steps
            if step.port_call_id == call.id
        ],
        active_incidents=active_incidents,
        recovery_proposals=proposals,
        advisory_only=True,
        requires_human_approval=True,
        actuation_allowed=False,
    )


@app.get("/api/v1/service-duration-calibrations")
def service_duration_calibrations():
    rows = sorted(
        sim.service_duration_calibrations,
        key=lambda item: item.service_kind.value,
    )
    return {"count": len(rows), "calibrations": rows}


@app.post("/api/v1/service-duration-calibrations")
def update_service_duration_calibration(
    req: ServiceDurationCalibrationRequest,
    identity: OperatorIdentity = Depends(recovery_approver),
):
    if req.observed_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="observed_at must include a timezone")

    received_at = datetime.now(timezone.utc).replace(microsecond=0)
    observed_at = req.observed_at.astimezone(timezone.utc).replace(microsecond=0)
    freshness_seconds = max(0, int((received_at - observed_at).total_seconds()))
    stale = freshness_seconds > req.stale_after_seconds
    provenance = DataSourceProvenance(
        source_id=req.source_id,
        domain=DataDomain.SERVICE_CALIBRATION,
        mode=req.mode,
        provider=req.provider,
        observed_at=observed_at,
        received_at=received_at,
        freshness_seconds=freshness_seconds,
        stale_after_seconds=req.stale_after_seconds,
        stale=stale,
        health=AdapterHealth.STALE if stale else AdapterHealth.HEALTHY,
        record_count=1,
        detail=req.detail,
        last_success_at=received_at if not stale else None,
    )
    calibration = ServiceDurationCalibration(
        service_kind=req.service_kind,
        duration_minutes=req.duration_minutes,
        source_id=req.source_id,
        mode=req.mode,
        provider=req.provider,
        observed_at=observed_at,
        detail=req.detail,
    )

    try:
        updated = sim.set_service_duration_calibration(
            calibration,
            provenance,
            updated_by=identity.operator_id,
            updated_role=identity.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    metrics.inc("portflow_calibration_updates_total")
    return {
        "calibration": updated,
        "provenance": provenance,
        "updated_by": identity,
    }



@app.get("/api/v1/adapters")
def adapters():
    return list_adapter_snapshots()


@app.get("/api/v1/adapters/{adapter_id}/preview")
def adapter_preview(adapter_id: str):
    snapshot = get_adapter_snapshot(adapter_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Unknown adapter: {adapter_id}")
    return snapshot


@app.post("/api/v1/adapters/{adapter_id}/ingest")
def adapter_ingest(
    adapter_id: str,
    identity: OperatorIdentity = Depends(recovery_approver),
):
    snapshot = get_adapter_snapshot(adapter_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Unknown adapter: {adapter_id}")

    try:
        applied = sim.ingest_adapter_snapshot(
            snapshot,
            ingested_by=identity.operator_id,
            ingested_role=identity.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    metrics.inc("portflow_adapter_ingests_total")
    return {
        "adapter": snapshot.provenance,
        "applied_records": applied,
        "ingested_by": {
            "operator_id": identity.operator_id,
            "display_name": identity.display_name,
            "role": identity.role,
        },
        "harbor": sim.overview(),
    }


@app.get("/api/v1/scenarios")
def scenarios():
    return list_scenarios()


@app.post("/api/v1/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: str):
    global sim

    scenario = get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")

    store.clear_demo_state()
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
        recovery_proposal_evidence_sink=store.save_recovery_proposal_evidence,
    )

    for action in scenario.actions:
        if action.action_type.value == "connectivity":
            if action.link_mode is None:
                raise HTTPException(status_code=500, detail="Scenario connectivity action missing link_mode")
            sim.set_connectivity(action.link_mode)
        elif action.action_type.value == "incident":
            if action.incident_type is None:
                raise HTTPException(status_code=500, detail="Scenario incident action missing incident_type")
            sim.inject_incident(
                incident_type=action.incident_type,
                target_port_call_id=action.target_port_call_id,
                impact_minutes=action.impact_minutes,
            )

    harbor = sim.overview()
    proposals = sim.generate_recovery_proposals(
        evidence_trigger="scenario",
    )
    scenario_evidence = ScenarioRunEvidence(
        run_id=f"scenario-run-{uuid4().hex[:20]}",
        ran_at=datetime.now(timezone.utc).replace(microsecond=0),
        scenario=scenario,
        harbor=harbor,
        recovery_proposals=proposals,
    )
    store.save_scenario_run_evidence(scenario_evidence)
    metrics.inc("portflow_scenario_runs_total")

    return {
        "scenario": scenario,
        "harbor": harbor,
        "recovery_proposals": proposals,
        "evidence_run_id": scenario_evidence.run_id,
    }


@app.get("/api/v1/harbor")
def harbor():
    return sim.overview()


@app.post("/api/v1/connectivity")
def connectivity(req: ConnectivityRequest):
    sim.set_connectivity(req.mode)
    return sim.connectivity


@app.get("/api/v1/events")
def events(limit: int = 100):
    return store.list_events(limit=limit)


@app.get("/api/v1/incidents")
def incidents(limit: int = 100):
    return store.list_incidents(limit=limit)


@app.post("/api/v1/incidents")
def create_incident(req: IncidentRequest):
    try:
        return sim.inject_incident(
            incident_type=req.incident_type,
            target_port_call_id=req.target_port_call_id,
            impact_minutes=req.impact_minutes,
            target_resource_id=req.target_resource_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/v1/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str):
    try:
        return sim.resolve_incident(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/recovery/proposals")
def recovery_proposals(call_id: str | None = None):
    proposals = sim.generate_recovery_proposals(call_id=call_id)
    return {
        "count": len(proposals),
        "proposals": proposals,
        "auto_apply": False,
        "authority": "operator_or_supervisor",
    }


@app.post("/api/v1/recovery/proposals/{proposal_id}/apply")
def apply_recovery_proposal(
    proposal_id: str,
    identity: OperatorIdentity = Depends(recovery_approver),
):
    try:
        receipt = sim.apply_recovery_proposal(
            proposal_id,
            approved_by=identity.operator_id,
            approved_role=identity.role,
            approved_display_name=identity.display_name,
        )
        metrics.inc("portflow_recovery_approvals_total")
        return receipt
    except RecoveryProposalStaleError as exc:
        metrics.inc("portflow_recovery_contingencies_total")
        raise HTTPException(
            status_code=409,
            detail={
                "code": "recovery_proposal_stale",
                **exc.contingency.model_dump(mode="json"),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/recovery/receipts")
def recovery_receipts(
    limit: int = 100,
    identity: OperatorIdentity = Depends(current_operator),
):
    return store.list_recovery_receipts(limit=limit)


@app.get("/api/v1/evidence/recovery-proposals")
def recovery_proposal_evidence(
    limit: int = 100,
    identity: OperatorIdentity = Depends(current_operator),
):
    return {
        "count": len(store.list_recovery_proposal_evidence(limit=limit)),
        "evidence": store.list_recovery_proposal_evidence(limit=limit),
    }


@app.get("/api/v1/evidence/scenario-runs")
def scenario_run_evidence(
    limit: int = 100,
    scenario_id: str | None = None,
    identity: OperatorIdentity = Depends(current_operator),
):
    evidence = store.list_scenario_run_evidence(
        limit=limit,
        scenario_id=scenario_id,
    )
    return {
        "count": len(evidence),
        "evidence": evidence,
    }


@app.get("/api/v1/evidence/scenario-runs/{run_id}/pack")
def scenario_run_evidence_pack(
    run_id: str,
    identity: OperatorIdentity = Depends(current_operator),
):
    evidence = store.get_scenario_run_evidence(run_id)
    if evidence is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario evidence run: {run_id}",
        )

    scenario_run = evidence.model_dump(mode="json")
    canonical = json.dumps(
        scenario_run,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return {
        "pack_version": "portflow-evidence-v1",
        "sha256": digest,
        "scenario_run": evidence,
        "replay_input": {
            "scenario_id": evidence.scenario.id,
            "actions": evidence.scenario.actions,
        },
    }


@app.get("/api/v1/replay/pending")
def replay_pending():
    return {
        "pending": store.pending_outbound_count(),
        "events": store.pending_outbound_events(limit=200),
    }


@app.get("/api/v1/replay/receipts")
def replay_receipts(limit: int = 100):
    return store.list_replay_receipts(limit=limit)


@app.post("/api/v1/replay")
def replay_now():
    receipts = store.replay_outbound_events(lambda event: True)
    metrics.inc("portflow_replay_acks_total", len(receipts))
    sim._refresh_queued_count()
    sim._persist()
    return {
        "replayed": len(receipts),
        "pending": store.pending_outbound_count(),
        "receipts": receipts,
    }


@app.get("/api/v1/port-calls/{call_id}/dependency-graph")
def dependency_graph(call_id: str):
    try:
        return sim.dependency_graph(call_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/berth-conflicts")
def berth_conflicts():
    return [conflict.__dict__ for conflict in detect_berth_conflicts(sim.port_calls)]


@app.get("/api/v1/port-calls/{call_id}/risk")
def port_call_risk(call_id: str):
    call = next((candidate for candidate in sim.port_calls if candidate.id == call_id), None)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Unknown port call: {call_id}")
    conflicts = detect_berth_conflicts(sim.port_calls)
    conflicted_ids = {x.first_call_id for x in conflicts} | {x.second_call_id for x in conflicts}
    level, score, reasons = score_port_call(call, sim.weather, call.id in conflicted_ids)
    return {"found": True, "call_id": call.id, "risk": level, "score": score, "reasons": reasons}


@app.post("/api/v1/demo/reset")
def reset_demo():
    global sim
    store.clear_demo_state()
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
        recovery_proposal_evidence_sink=store.save_recovery_proposal_evidence,
    )
    return sim.overview()


@app.websocket("/ws/harbor")
async def harbor_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(sim.overview().model_dump(mode="json"))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return

def _mount_optional_static_frontend() -> None:
    static_dir = os.getenv("PORTFLOW_STATIC_DIR")
    if not static_dir:
        return

    static_path = os.path.abspath(static_dir)
    index_path = os.path.join(static_path, "index.html")
    if not os.path.isdir(static_path) or not os.path.isfile(index_path):
        raise RuntimeError(
            "PORTFLOW_STATIC_DIR must contain a built frontend with index.html"
        )

    app.mount(
        "/",
        StaticFiles(directory=static_path, html=True),
        name="portflow-frontend",
    )


_mount_optional_static_frontend()
