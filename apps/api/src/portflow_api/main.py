from __future__ import annotations

import asyncio
import hashlib
import json
import os
from uuid import uuid4
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .adapters import get_adapter_snapshot, list_adapter_snapshots
from .domain import detect_berth_conflicts, score_port_call
from .observability import metrics, observe_http
from .models import (
    AdapterHealth, DataDomain, DataSourceMode, DataSourceProvenance, IncidentType,
    LinkMode, OperatorIdentity, ScenarioRunEvidence, ServiceDurationCalibration, ServiceKind,
)
from .simulator import HarborSimulator, RecoveryProposalStaleError
from .security import configured_approvers, current_operator, recovery_approver
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


app = FastAPI(title="PortFlow API", version="0.15.0", lifespan=lifespan)
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
        "version": "0.15.0",
    }


@app.get("/readyz")
def readyz():
    schema = store.schema_status()
    authorization_configured = bool(configured_approvers())
    ready = (
        _runtime_ready
        and bool(schema["database_reachable"])
        and bool(schema["compatible"])
    )
    payload = {
        "ok": ready,
        "service": "portflow-api",
        "version": "0.15.0",
        "runtime_ready": _runtime_ready,
        "schema_mode": _schema_mode,
        "schema": schema,
        "authorization_configured": authorization_configured,
    }
    if not ready:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.get("/metrics")
def prometheus_metrics():
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
