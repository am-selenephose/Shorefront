from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import random
from typing import Callable
from uuid import uuid4

from .domain import detect_berth_conflicts, extend_departure, score_port_call, shift_call_from_stage
from .models import (
    AdapterHealth, AdapterSnapshot, Berth, BerthStatus, ConnectivityState,
    Coordinate, DataDomain, DataSourceMode, DataSourceProvenance, HarborOverview,
    Incident, IncidentStatus, IncidentType, LinkMode, OperationsEvent,
    PortCall, PortCallStage, RecoveryAction, RecoveryActionType,
    RecoveryApplicationReceipt, RecoveryProposal, ResourceStatus, RiskLevel,
    OperatorRole, ServiceKind, ServiceResource, ServiceState, ServiceStep, Vessel, VesselStatus,
    WeatherState,
)


EventSink = Callable[[OperationsEvent], None]
IncidentSink = Callable[[Incident], None]
SnapshotSink = Callable[[HarborOverview], None]
SpoolSink = Callable[[OperationsEvent], bool]
ReplaySink = Callable[[], int]
PendingCount = Callable[[], int]
RecoveryReceiptSink = Callable[[RecoveryApplicationReceipt], bool]


class HarborSimulator:
    def __init__(
        self,
        seed: int = 42,
        initial: HarborOverview | None = None,
        event_sink: EventSink | None = None,
        incident_sink: IncidentSink | None = None,
        snapshot_sink: SnapshotSink | None = None,
        spool_sink: SpoolSink | None = None,
        replay_sink: ReplaySink | None = None,
        pending_count: PendingCount | None = None,
        recovery_receipt_sink: RecoveryReceiptSink | None = None,
    ):
        self.rng = random.Random(seed)
        self.event_sink = event_sink
        self.incident_sink = incident_sink
        self.snapshot_sink = snapshot_sink
        self.spool_sink = spool_sink
        self.replay_sink = replay_sink
        self.pending_count = pending_count
        self.recovery_receipt_sink = recovery_receipt_sink
        self.tick_count = 0

        if initial is not None:
            self._restore(initial)
            return

        self.port_name = "PortFlow Demo Harbor"
        self.center = Coordinate(lat=51.948, lon=4.142)
        self._started = datetime.now(timezone.utc).replace(microsecond=0)
        self.vessels = self._make_vessels()
        self.berths = self._make_berths()
        self.port_calls = self._make_port_calls()
        self.weather = WeatherState(
            observed_at=self._started,
            wind_knots=19.0,
            gust_knots=26.0,
            visibility_km=9.4,
            wave_height_m=1.2,
            tide_m=0.8,
            restriction_active=False,
        )
        self.connectivity = ConnectivityState(
            mode=LinkMode.FULL,
            primary_link="Fiber / LTE",
            fallback_link="Satellite",
            bandwidth_kbps=50000,
            queued_events=0,
            last_transition_at=self._started,
        )
        self.incidents: list[Incident] = []
        self.data_sources = self._default_data_sources()
        self.service_resources = self._make_service_resources()
        self.service_steps = self._make_service_steps()
        self.events: list[OperationsEvent] = []
        self._recalculate_services()
        self._emit("system", RiskLevel.LOW, "Operations picture initialized", "Synthetic harbor state is live.")
        self._persist()

    def _restore(self, state: HarborOverview) -> None:
        self.port_name = state.port_name
        self.center = deepcopy(state.center)
        self._started = state.generated_at
        self.vessels = deepcopy(state.vessels)
        self.berths = deepcopy(state.berths)
        self.port_calls = deepcopy(state.port_calls)
        self.weather = deepcopy(state.weather)
        self.connectivity = deepcopy(state.connectivity)
        self.incidents = deepcopy(state.incidents)
        self.data_sources = deepcopy(state.data_sources) or self._default_data_sources()
        self.service_resources = deepcopy(state.service_resources)
        self.service_steps = deepcopy(state.service_steps)
        self.events = deepcopy(state.events)

        # Backward-compatible restore for snapshots created before v0.3.
        if not self.service_resources:
            self.service_resources = self._make_service_resources()
        else:
            existing_ids = {resource.id for resource in self.service_resources}
            for resource in self._make_service_resources():
                if resource.id not in existing_ids:
                    self.service_resources.append(resource)
        expected_service_kinds = {
            ServiceKind.PILOT,
            ServiceKind.TUG,
            ServiceKind.BERTH,
            ServiceKind.CRANE,
            ServiceKind.CARGO,
            ServiceKind.BUNKER,
            ServiceKind.STORES,
            ServiceKind.DOCUMENTS,
            ServiceKind.CUSTOMS,
            ServiceKind.GATE,
            ServiceKind.DEPARTURE,
        }
        service_kinds_by_call: dict[str, set[ServiceKind]] = {}
        for step in self.service_steps:
            service_kinds_by_call.setdefault(step.port_call_id, set()).add(step.kind)
        service_graph_complete = bool(self.service_steps) and all(
            expected_service_kinds.issubset(service_kinds_by_call.get(call.id, set()))
            for call in self.port_calls
        )
        if not service_graph_complete:
            self.service_steps = self._make_service_steps()

        self._refresh_queued_count()
        self._recalculate_services()
        self._recalculate_risks()


    def _default_data_sources(self) -> list[DataSourceProvenance]:
        now = self._started
        return [
            DataSourceProvenance(
                source_id="synthetic-ais",
                domain=DataDomain.AIS,
                mode=DataSourceMode.SYNTHETIC,
                provider="PortFlow synthetic harbor generator",
                observed_at=now,
                received_at=now,
                freshness_seconds=0,
                stale_after_seconds=10_000_000,
                stale=False,
                health=AdapterHealth.HEALTHY,
                record_count=len(getattr(self, "vessels", [])),
                detail="Synthetic vessel positions for the portfolio demo.",
            ),
            DataSourceProvenance(
                source_id="synthetic-weather",
                domain=DataDomain.WEATHER_TIDE,
                mode=DataSourceMode.SYNTHETIC,
                provider="PortFlow synthetic metocean generator",
                observed_at=now,
                received_at=now,
                freshness_seconds=0,
                stale_after_seconds=10_000_000,
                stale=False,
                health=AdapterHealth.HEALTHY,
                record_count=1,
                detail="Synthetic weather and tide state for the portfolio demo.",
            ),
            DataSourceProvenance(
                source_id="synthetic-berth-plan",
                domain=DataDomain.BERTH_PLAN,
                mode=DataSourceMode.SYNTHETIC,
                provider="PortFlow synthetic berth-plan generator",
                observed_at=now,
                received_at=now,
                freshness_seconds=0,
                stale_after_seconds=10_000_000,
                stale=False,
                health=AdapterHealth.HEALTHY,
                record_count=len(getattr(self, "port_calls", [])),
                detail="Synthetic berth allocations and port-call timing.",
            ),
        ]

    def _refresh_data_source_freshness(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for source in self.data_sources:
            if source.mode == DataSourceMode.SYNTHETIC:
                source.freshness_seconds = 0
                source.stale = False
                source.health = AdapterHealth.HEALTHY
                continue

            age = max(0, int((now - source.observed_at).total_seconds()))
            source.freshness_seconds = age
            source.stale = age > source.stale_after_seconds

            if source.stale and source.health in {
                AdapterHealth.HEALTHY,
                AdapterHealth.DEGRADED,
            }:
                source.health = AdapterHealth.STALE
            elif not source.stale and source.health == AdapterHealth.STALE:
                source.health = AdapterHealth.HEALTHY

    def _active_source_ids(self) -> set[str]:
        return (
            {vessel.source_id for vessel in self.vessels}
            | {berth.source_id for berth in self.berths}
            | {call.source_id for call in self.port_calls}
            | {self.weather.source_id}
        )

    def _prune_data_sources(self) -> None:
        active_ids = self._active_source_ids()
        self.data_sources = [
            source for source in self.data_sources
            if source.source_id in active_ids
        ]

    def _upsert_data_source(self, provenance: DataSourceProvenance) -> None:
        self.data_sources = [
            item for item in self.data_sources
            if item.source_id != provenance.source_id
        ]
        self.data_sources.append(deepcopy(provenance))
        self._prune_data_sources()
        self.data_sources.sort(key=lambda item: (item.domain.value, item.source_id))

    def _validated_adapter_records(self, snapshot: AdapterSnapshot) -> list[dict]:
        domain = snapshot.provenance.domain
        normalized: list[dict] = []

        try:
            if domain == DataDomain.AIS:
                for record in snapshot.records:
                    vessel_id = str(record["vessel_id"]).strip()
                    if not vessel_id:
                        raise ValueError("AIS vessel_id must be non-empty")

                    lat = float(record["lat"])
                    lon = float(record["lon"])
                    speed = float(record["speed_knots"]) if record.get("speed_knots") is not None else None
                    heading = float(record["heading_deg"]) if record.get("heading_deg") is not None else None
                    eta_offset = int(record["eta_offset_minutes"]) if record.get("eta_offset_minutes") is not None else None

                    if not -90 <= lat <= 90:
                        raise ValueError("AIS latitude out of range")
                    if not -180 <= lon <= 180:
                        raise ValueError("AIS longitude out of range")
                    if speed is not None and speed < 0:
                        raise ValueError("AIS speed cannot be negative")
                    if heading is not None and not 0 <= heading < 360:
                        raise ValueError("AIS heading out of range")

                    normalized.append(dict(
                        vessel_id=vessel_id,
                        lat=lat,
                        lon=lon,
                        speed_knots=speed,
                        heading_deg=heading,
                        eta_offset_minutes=eta_offset,
                    ))

            elif domain == DataDomain.WEATHER_TIDE:
                if not snapshot.records:
                    raise ValueError("Weather adapter snapshot contains no records")

                record = snapshot.records[0]
                normalized_record = dict(
                    wind_knots=float(record["wind_knots"]),
                    gust_knots=float(record["gust_knots"]),
                    visibility_km=float(record["visibility_km"]),
                    wave_height_m=float(record["wave_height_m"]),
                    tide_m=float(record["tide_m"]),
                )
                if normalized_record["wind_knots"] < 0 or normalized_record["gust_knots"] < 0:
                    raise ValueError("Weather wind values cannot be negative")
                if normalized_record["visibility_km"] < 0:
                    raise ValueError("Weather visibility cannot be negative")
                if normalized_record["wave_height_m"] < 0:
                    raise ValueError("Wave height cannot be negative")
                normalized.append(normalized_record)

            elif domain == DataDomain.BERTH_PLAN:
                known_berths = {berth.id for berth in self.berths}
                known_calls = {call.id for call in self.port_calls}

                for record in snapshot.records:
                    port_call_id = str(record["port_call_id"]).strip()
                    berth_id = str(record["berth_id"]).strip()
                    arrival_offset = int(record["arrival_offset_minutes"])
                    departure_offset = int(record["departure_offset_minutes"])

                    if not port_call_id or not berth_id:
                        raise ValueError("Berth-plan identifiers must be non-empty")
                    if departure_offset <= arrival_offset:
                        raise ValueError("Berth-plan departure must be after arrival")
                    if port_call_id in known_calls and berth_id not in known_berths:
                        raise ValueError("Berth-plan references an unknown berth")

                    normalized.append(dict(
                        port_call_id=port_call_id,
                        berth_id=berth_id,
                        arrival_offset_minutes=arrival_offset,
                        departure_offset_minutes=departure_offset,
                    ))

            else:
                raise ValueError("Unsupported adapter domain: " + domain.value)

        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("Unsupported adapter domain"):
                raise
            raise ValueError(
                "Invalid " + domain.value + " adapter payload: " + str(exc)
            ) from exc

        return normalized

    def ingest_adapter_snapshot(
        self,
        snapshot: AdapterSnapshot,
        ingested_by: str | None = None,
        ingested_role: OperatorRole | None = None,
    ) -> int:
        provenance = snapshot.provenance
        if provenance.stale or provenance.health in {
            AdapterHealth.STALE,
            AdapterHealth.OFFLINE,
            AdapterHealth.ERROR,
            AdapterHealth.UNCONFIGURED,
        }:
            raise ValueError(
                f"Adapter {snapshot.adapter_id} is not ingestible: {provenance.health.value}"
            )

        records = self._validated_adapter_records(snapshot)
        applied = 0

        if provenance.domain == DataDomain.AIS:
            by_id = {vessel.id: vessel for vessel in self.vessels}
            for record in records:
                vessel = by_id.get(str(record.get("vessel_id", "")))
                if vessel is None:
                    continue
                vessel.position.lat = float(record["lat"])
                vessel.position.lon = float(record["lon"])
                if record.get("speed_knots") is not None:
                    vessel.speed_knots = float(record["speed_knots"])
                if record.get("heading_deg") is not None:
                    vessel.heading_deg = float(record["heading_deg"])
                if record.get("eta_offset_minutes") is not None:
                    vessel.eta = self._started + timedelta(
                        minutes=int(record["eta_offset_minutes"])
                    )
                vessel.source_id = provenance.source_id
                applied += 1

        elif provenance.domain == DataDomain.WEATHER_TIDE:
            if not records:
                raise ValueError("Weather adapter snapshot contains no records")
            record = records[0]
            self.weather.wind_knots = float(record["wind_knots"])
            self.weather.gust_knots = float(record["gust_knots"])
            self.weather.visibility_km = float(record["visibility_km"])
            self.weather.wave_height_m = float(record["wave_height_m"])
            self.weather.tide_m = float(record["tide_m"])
            self.weather.observed_at = provenance.observed_at
            self.weather.source_id = provenance.source_id
            applied = 1
            self._recalculate_risks()

        elif provenance.domain == DataDomain.BERTH_PLAN:
            calls = {call.id: call for call in self.port_calls}
            vessels = {vessel.id: vessel for vessel in self.vessels}
            berths = {berth.id: berth for berth in self.berths}
            for record in records:
                call = calls.get(str(record.get("port_call_id", "")))
                if call is None:
                    continue

                old_arrival = call.arrival_eta
                new_arrival = self._started + timedelta(
                    minutes=int(record["arrival_offset_minutes"])
                )
                new_departure = self._started + timedelta(
                    minutes=int(record["departure_offset_minutes"])
                )
                delta = new_arrival - old_arrival

                call.arrival_eta = new_arrival
                call.departure_eta = new_departure
                call.berth_id = str(record["berth_id"])
                call.source_id = provenance.source_id

                berth = berths.get(call.berth_id)
                if berth is not None:
                    berth.source_id = provenance.source_id

                for stage in call.stages:
                    stage.planned_at = stage.planned_at + delta

                vessel = vessels.get(call.vessel_id)
                if vessel is not None:
                    vessel.assigned_berth_id = call.berth_id

                berth_step = next(
                    (
                        step for step in self.service_steps
                        if step.port_call_id == call.id and step.kind == ServiceKind.BERTH
                    ),
                    None,
                )
                if berth_step:
                    berth_step.resource_id = call.berth_id

                applied += 1

            self._recalculate_services()
            self._recalculate_risks()

        else:
            raise ValueError(f"Unsupported adapter domain: {provenance.domain.value}")

        if applied == 0:
            raise ValueError(
                f"Adapter {snapshot.adapter_id} contained no records matching modeled harbor entities"
            )

        self._upsert_data_source(provenance)
        self._emit(
            "data_adapter",
            RiskLevel.LOW,
            f"Adapter ingested: {snapshot.adapter_id}",
            (
                f"{applied} {provenance.domain.value} record(s) ingested from "
                f"{provenance.mode.value} source {provenance.provider}; "
                f"freshness {provenance.freshness_seconds}s."
            ),
            actor_id=ingested_by,
            actor_role=ingested_role,
            source_id=provenance.source_id,
        )
        self._persist()
        return applied

    def _make_vessels(self) -> list[Vessel]:
        now = self._started
        return [
            Vessel(id="v-aurora", name="MSC Aurora", imo="9991001", vessel_type="Container",
                   status=VesselStatus.INBOUND, position=Coordinate(lat=51.989, lon=3.970),
                   speed_knots=11.8, heading_deg=92, eta=now+timedelta(minutes=54),
                   assigned_berth_id="b-12", cargo_summary="8,420 TEU mixed container"),
            Vessel(id="v-lima", name="Maersk Lima", imo="9991002", vessel_type="Container",
                   status=VesselStatus.AT_ANCHOR, position=Coordinate(lat=52.010, lon=3.910),
                   speed_knots=0.2, heading_deg=180, eta=now+timedelta(minutes=88),
                   assigned_berth_id="b-09", cargo_summary="6,100 TEU mixed container"),
            Vessel(id="v-glory", name="Ever Glory", imo="9991003", vessel_type="Container",
                   status=VesselStatus.MANEUVERING, position=Coordinate(lat=51.963, lon=4.045),
                   speed_knots=6.4, heading_deg=104, eta=now+timedelta(minutes=22),
                   assigned_berth_id="b-07", cargo_summary="4,780 TEU"),
            Vessel(id="v-nordic", name="Nordic Atlas", imo="9991004", vessel_type="Product tanker",
                   status=VesselStatus.BERTHED, position=Coordinate(lat=51.934, lon=4.155),
                   speed_knots=0, heading_deg=0, assigned_berth_id="b-03",
                   cargo_summary="Refined products"),
            Vessel(id="v-seaway", name="Seaway Polaris", imo="9991005", vessel_type="Ro-Ro",
                   status=VesselStatus.OUTBOUND, position=Coordinate(lat=51.968, lon=4.010),
                   speed_knots=9.2, heading_deg=274, cargo_summary="Vehicles / project cargo"),
            Vessel(id="v-nova", name="Ocean Nova", imo="9991006", vessel_type="Container",
                   status=VesselStatus.AT_ANCHOR, position=Coordinate(lat=52.018, lon=3.885),
                   speed_knots=0.1, heading_deg=180, eta=now+timedelta(hours=7, minutes=35),
                   assigned_berth_id="b-07", cargo_summary="3,960 TEU"),
        ]

    def _make_berths(self) -> list[Berth]:
        return [
            Berth(id="b-03", name="Berth 03", terminal="Liquid Bulk", status=BerthStatus.OCCUPIED,
                  max_length_m=310, position=Coordinate(lat=51.934, lon=4.155), vessel_id="v-nordic"),
            Berth(id="b-07", name="Berth 07", terminal="Delta Container", status=BerthStatus.RESERVED,
                  max_length_m=400, position=Coordinate(lat=51.951, lon=4.133), vessel_id="v-glory"),
            Berth(id="b-09", name="Berth 09", terminal="Delta Container", status=BerthStatus.RESERVED,
                  max_length_m=400, position=Coordinate(lat=51.947, lon=4.119), vessel_id="v-lima"),
            Berth(id="b-12", name="Berth 12", terminal="Maas Container", status=BerthStatus.RESERVED,
                  max_length_m=420, position=Coordinate(lat=51.942, lon=4.101), vessel_id="v-aurora"),
            Berth(id="b-15", name="Berth 15", terminal="Maas Container", status=BerthStatus.AVAILABLE,
                  max_length_m=420, position=Coordinate(lat=51.938, lon=4.083)),
        ]

    def _stages(self, arrival: datetime) -> list[PortCallStage]:
        specs = [
            ("notice", "Arrival notice accepted", -90, []),
            ("pilot", "Pilot ordered", -55, ["notice"]),
            ("pilot_board", "Pilot aboard", -35, ["pilot"]),
            ("tug", "Tug rendezvous", -22, ["pilot_board"]),
            ("berth", "All fast at berth", 0, ["tug"]),
            ("cargo", "Cargo operations", 35, ["berth"]),
            ("services", "Bunkers / stores / services", 70, ["berth"]),
            ("departure", "Departure clearance", 360, ["cargo", "services"]),
        ]
        return [
            PortCallStage(code=code, label=label, planned_at=arrival+timedelta(minutes=offset), dependency_codes=deps)
            for code, label, offset, deps in specs
        ]

    def _make_port_calls(self) -> list[PortCall]:
        now = self._started
        return [
            PortCall(id="pc-aurora", vessel_id="v-aurora", berth_id="b-12",
                     arrival_eta=now+timedelta(minutes=54), departure_eta=now+timedelta(hours=9),
                     stages=self._stages(now+timedelta(minutes=54))),
            PortCall(id="pc-lima", vessel_id="v-lima", berth_id="b-09",
                     arrival_eta=now+timedelta(minutes=88), departure_eta=now+timedelta(hours=11),
                     stages=self._stages(now+timedelta(minutes=88))),
            PortCall(id="pc-glory", vessel_id="v-glory", berth_id="b-07",
                     arrival_eta=now+timedelta(minutes=22), departure_eta=now+timedelta(hours=7),
                     stages=self._stages(now+timedelta(minutes=22))),
            PortCall(id="pc-nova", vessel_id="v-nova", berth_id="b-07",
                     arrival_eta=now+timedelta(hours=7, minutes=35),
                     departure_eta=now+timedelta(hours=14),
                     stages=self._stages(now+timedelta(hours=7, minutes=35))),
        ]

    def _make_service_resources(self) -> list[ServiceResource]:
        return [
            ServiceResource(
                id="pilot-alpha", kind=ServiceKind.PILOT, name="Pilot Alpha",
                status=ResourceStatus.ASSIGNED, capacity=2,
                assigned_port_call_ids=["pc-aurora", "pc-glory"],
            ),
            ServiceResource(
                id="pilot-bravo", kind=ServiceKind.PILOT, name="Pilot Bravo",
                status=ResourceStatus.ASSIGNED, capacity=2,
                assigned_port_call_ids=["pc-lima", "pc-nova"],
            ),
            ServiceResource(
                id="tug-14", kind=ServiceKind.TUG, name="Tug 14",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-aurora", "pc-glory"],
            ),
            ServiceResource(
                id="tug-22", kind=ServiceKind.TUG, name="Tug 22",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-lima", "pc-nova"],
            ),
            ServiceResource(
                id="tug-31", kind=ServiceKind.TUG, name="Tug 31",
                status=ResourceStatus.AVAILABLE, capacity=1,
                assigned_port_call_ids=[],
                available_from=self._started + timedelta(minutes=20),
            ),
            ServiceResource(
                id="b-07", kind=ServiceKind.BERTH, name="Berth 07",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-glory", "pc-nova"],
            ),
            ServiceResource(
                id="b-09", kind=ServiceKind.BERTH, name="Berth 09",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-lima"],
            ),
            ServiceResource(
                id="b-12", kind=ServiceKind.BERTH, name="Berth 12",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-aurora"],
            ),
            ServiceResource(
                id="b-15", kind=ServiceKind.BERTH, name="Berth 15",
                status=ResourceStatus.AVAILABLE, capacity=1,
                assigned_port_call_ids=[],
            ),
            ServiceResource(
                id="crane-b07-a", kind=ServiceKind.CRANE, name="B07 Crane A",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-glory", "pc-nova"],
            ),
            ServiceResource(
                id="crane-b09-a", kind=ServiceKind.CRANE, name="B09 Crane A",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-lima"],
            ),
            ServiceResource(
                id="crane-b12-a", kind=ServiceKind.CRANE, name="B12 Crane A",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-aurora"],
            ),
            ServiceResource(
                id="crane-b15-a", kind=ServiceKind.CRANE, name="B15 Crane A",
                status=ResourceStatus.AVAILABLE, capacity=1,
                assigned_port_call_ids=[],
            ),
            ServiceResource(
                id="bunker-barge-4", kind=ServiceKind.BUNKER, name="Bunker Barge 4",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-aurora", "pc-glory"],
            ),
            ServiceResource(
                id="bunker-barge-9", kind=ServiceKind.BUNKER, name="Bunker Barge 9",
                status=ResourceStatus.ASSIGNED, capacity=1,
                assigned_port_call_ids=["pc-lima", "pc-nova"],
            ),
            ServiceResource(
                id="bunker-barge-12", kind=ServiceKind.BUNKER, name="Bunker Barge 12",
                status=ResourceStatus.AVAILABLE, capacity=1,
                assigned_port_call_ids=[],
                available_from=self._started + timedelta(minutes=100),
            ),
            ServiceResource(
                id="stores-team-1", kind=ServiceKind.STORES, name="Stores Team 1",
                status=ResourceStatus.ASSIGNED, capacity=4,
                assigned_port_call_ids=["pc-aurora", "pc-lima", "pc-glory", "pc-nova"],
            ),
            ServiceResource(
                id="docs-desk-1", kind=ServiceKind.DOCUMENTS, name="Docs Desk 1",
                status=ResourceStatus.ASSIGNED, capacity=4,
                assigned_port_call_ids=["pc-aurora", "pc-lima", "pc-glory", "pc-nova"],
            ),
            ServiceResource(
                id="gate-team-1", kind=ServiceKind.GATE, name="Gate Team 1",
                status=ResourceStatus.ASSIGNED, capacity=4,
                assigned_port_call_ids=["pc-aurora", "pc-lima", "pc-glory", "pc-nova"],
            ),
            ServiceResource(
                id="customs-team-1", kind=ServiceKind.CUSTOMS, name="Customs Team 1",
                status=ResourceStatus.ASSIGNED, capacity=4,
                assigned_port_call_ids=["pc-aurora", "pc-lima", "pc-glory", "pc-nova"],
            ),
        ]

    def _resource_for(self, call: PortCall, kind: ServiceKind) -> str | None:
        candidates = [
            resource for resource in self.service_resources
            if resource.kind == kind and call.id in resource.assigned_port_call_ids
        ]
        return candidates[0].id if candidates else None

    def _stage_time(self, call: PortCall, code: str, fallback: datetime) -> datetime:
        stage = next((item for item in call.stages if item.code == code), None)
        return stage.planned_at if stage else fallback

    def _make_service_steps(self) -> list[ServiceStep]:
        steps: list[ServiceStep] = []

        for call in self.port_calls:
            times = {
                ServiceKind.PILOT: self._stage_time(call, "pilot", call.arrival_eta),
                ServiceKind.TUG: self._stage_time(call, "tug", call.arrival_eta),
                ServiceKind.BERTH: self._stage_time(call, "berth", call.arrival_eta),
                ServiceKind.CRANE: self._stage_time(call, "cargo", call.arrival_eta),
                ServiceKind.CARGO: self._stage_time(call, "cargo", call.arrival_eta) + timedelta(minutes=10),
                ServiceKind.BUNKER: self._stage_time(call, "services", call.arrival_eta) + timedelta(minutes=5),
                ServiceKind.STORES: self._stage_time(call, "services", call.arrival_eta) + timedelta(minutes=15),
                ServiceKind.DOCUMENTS: call.departure_eta - timedelta(minutes=120),
                ServiceKind.CUSTOMS: call.departure_eta - timedelta(minutes=60),
                ServiceKind.GATE: call.departure_eta - timedelta(minutes=35),
                ServiceKind.DEPARTURE: call.departure_eta,
            }

            labels = {
                ServiceKind.PILOT: "Pilot boarding",
                ServiceKind.TUG: "Tug rendezvous",
                ServiceKind.BERTH: "Berth access",
                ServiceKind.CRANE: "Crane allocation",
                ServiceKind.CARGO: "Cargo operation",
                ServiceKind.BUNKER: "Bunker service",
                ServiceKind.STORES: "Stores delivery",
                ServiceKind.DOCUMENTS: "Port-call documents",
                ServiceKind.CUSTOMS: "Customs release",
                ServiceKind.GATE: "Landside gate clearance",
                ServiceKind.DEPARTURE: "Departure clearance",
            }

            fixed_resources = {
                ServiceKind.BERTH: call.berth_id,
            }

            dependencies = {
                ServiceKind.PILOT: [],
                ServiceKind.TUG: [ServiceKind.PILOT],
                ServiceKind.BERTH: [ServiceKind.TUG],
                ServiceKind.CRANE: [ServiceKind.BERTH],
                ServiceKind.CARGO: [ServiceKind.CRANE],
                ServiceKind.BUNKER: [ServiceKind.BERTH],
                ServiceKind.STORES: [ServiceKind.BERTH],
                ServiceKind.DOCUMENTS: [ServiceKind.BERTH],
                ServiceKind.CUSTOMS: [ServiceKind.CARGO, ServiceKind.DOCUMENTS],
                ServiceKind.GATE: [ServiceKind.CARGO, ServiceKind.CUSTOMS],
                ServiceKind.DEPARTURE: [
                    ServiceKind.CARGO,
                    ServiceKind.BUNKER,
                    ServiceKind.STORES,
                    ServiceKind.CUSTOMS,
                    ServiceKind.GATE,
                ],
            }

            for kind in (
                ServiceKind.PILOT,
                ServiceKind.TUG,
                ServiceKind.BERTH,
                ServiceKind.CRANE,
                ServiceKind.CARGO,
                ServiceKind.BUNKER,
                ServiceKind.STORES,
                ServiceKind.DOCUMENTS,
                ServiceKind.CUSTOMS,
                ServiceKind.GATE,
                ServiceKind.DEPARTURE,
            ):
                resource_id = fixed_resources.get(kind) or self._resource_for(call, kind)
                dependency_ids = [
                    f"svc-{call.id}-{dependency.value}"
                    for dependency in dependencies[kind]
                ]

                steps.append(ServiceStep(
                    id=f"svc-{call.id}-{kind.value}",
                    port_call_id=call.id,
                    kind=kind,
                    label=labels[kind],
                    planned_at=times[kind],
                    state=ServiceState.ASSIGNED if resource_id else ServiceState.READY,
                    resource_id=resource_id,
                    dependency_step_ids=dependency_ids,
                ))

        return steps

    def _sync_service_times(self) -> None:
        by_call = {call.id: call for call in self.port_calls}
        for step in self.service_steps:
            call = by_call.get(step.port_call_id)
            if not call:
                continue

            if step.kind == ServiceKind.PILOT:
                step.planned_at = self._stage_time(call, "pilot", call.arrival_eta)
            elif step.kind == ServiceKind.TUG:
                step.planned_at = self._stage_time(call, "tug", call.arrival_eta)
            elif step.kind == ServiceKind.BERTH:
                step.planned_at = self._stage_time(call, "berth", call.arrival_eta)
            elif step.kind == ServiceKind.CRANE:
                step.planned_at = self._stage_time(call, "cargo", call.arrival_eta)
            elif step.kind == ServiceKind.CARGO:
                step.planned_at = self._stage_time(call, "cargo", call.arrival_eta) + timedelta(minutes=10)
            elif step.kind == ServiceKind.BUNKER:
                step.planned_at = self._stage_time(call, "services", call.arrival_eta) + timedelta(minutes=5)
            elif step.kind == ServiceKind.STORES:
                step.planned_at = self._stage_time(call, "services", call.arrival_eta) + timedelta(minutes=15)
            elif step.kind == ServiceKind.DOCUMENTS:
                step.planned_at = call.departure_eta - timedelta(minutes=120)
            elif step.kind == ServiceKind.CUSTOMS:
                step.planned_at = call.departure_eta - timedelta(minutes=60)
            elif step.kind == ServiceKind.GATE:
                step.planned_at = call.departure_eta - timedelta(minutes=35)
            elif step.kind == ServiceKind.DEPARTURE:
                step.planned_at = call.departure_eta

    def _recalculate_services(self) -> None:
        self._sync_service_times()

        for resource in self.service_resources:
            resource.status = (
                ResourceStatus.ASSIGNED
                if resource.assigned_port_call_ids
                else ResourceStatus.AVAILABLE
            )

        for step in self.service_steps:
            step.state = ServiceState.ASSIGNED if step.resource_id else ServiceState.READY

        active = [incident for incident in self.incidents if incident.status == IncidentStatus.ACTIVE]

        for incident in active:
            if incident.incident_type == IncidentType.PILOT_DELAY and incident.target_port_call_id:
                self._mark_step(incident.target_port_call_id, ServiceKind.PILOT, ServiceState.DELAYED)
                self._mark_resource_for_call(incident.target_port_call_id, ServiceKind.PILOT, ResourceStatus.DELAYED)
            elif incident.incident_type in {
                IncidentType.TUG_UNAVAILABLE,
                IncidentType.BUNKER_UNAVAILABLE,
            }:
                affected_kind = (
                    ServiceKind.TUG
                    if incident.incident_type == IncidentType.TUG_UNAVAILABLE
                    else ServiceKind.BUNKER
                )
                if incident.target_resource_id:
                    resource = next(
                        (item for item in self.service_resources if item.id == incident.target_resource_id),
                        None,
                    )
                    if resource:
                        resource.status = ResourceStatus.UNAVAILABLE
                    for step in self.service_steps:
                        if (
                            step.kind == affected_kind
                            and step.resource_id == incident.target_resource_id
                        ):
                            step.state = ServiceState.BLOCKED
                elif incident.target_port_call_id:
                    self._mark_step(
                        incident.target_port_call_id,
                        affected_kind,
                        ServiceState.BLOCKED,
                    )
                    self._mark_resource_for_call(
                        incident.target_port_call_id,
                        affected_kind,
                        ResourceStatus.UNAVAILABLE,
                    )
            elif incident.incident_type == IncidentType.WIND_RESTRICTION:
                for call in self.port_calls:
                    vessel = next((v for v in self.vessels if v.id == call.vessel_id), None)
                    if vessel and vessel.status in {
                        VesselStatus.INBOUND,
                        VesselStatus.AT_ANCHOR,
                        VesselStatus.MANEUVERING,
                    }:
                        self._mark_step(call.id, ServiceKind.PILOT, ServiceState.BLOCKED)
                        self._mark_step(call.id, ServiceKind.TUG, ServiceState.BLOCKED)

        conflicts = detect_berth_conflicts(self.port_calls)
        for conflict in conflicts:
            # Later call is the one waiting for the occupied berth.
            self._mark_step(conflict.second_call_id, ServiceKind.BERTH, ServiceState.BLOCKED)

        # Propagate delayed/blocked dependency state through the graph.
        by_id = {step.id: step for step in self.service_steps}
        for _ in range(8):
            changed = False
            for step in self.service_steps:
                deps = [by_id[dep] for dep in step.dependency_step_ids if dep in by_id]
                if any(dep.state == ServiceState.BLOCKED for dep in deps):
                    if step.state != ServiceState.BLOCKED:
                        step.state = ServiceState.BLOCKED
                        changed = True
                elif any(dep.state == ServiceState.DELAYED for dep in deps):
                    if step.state not in {ServiceState.BLOCKED, ServiceState.DELAYED}:
                        step.state = ServiceState.DELAYED
                        changed = True
            if not changed:
                break

    def _mark_step(self, call_id: str, kind: ServiceKind, state: ServiceState) -> None:
        step = next(
            (item for item in self.service_steps if item.port_call_id == call_id and item.kind == kind),
            None,
        )
        if step:
            step.state = state

    def _mark_resource_for_call(
        self,
        call_id: str,
        kind: ServiceKind,
        status: ResourceStatus,
    ) -> None:
        resource = next(
            (
                item for item in self.service_resources
                if item.kind == kind and call_id in item.assigned_port_call_ids
            ),
            None,
        )
        if resource:
            resource.status = status

    def dependency_graph(self, call_id: str) -> dict:
        call = self._find_call(call_id, call_id)
        steps = sorted(
            [step for step in self.service_steps if step.port_call_id == call.id],
            key=lambda item: item.planned_at,
        )
        resources = {resource.id: resource for resource in self.service_resources}
        return {
            "port_call_id": call.id,
            "vessel_id": call.vessel_id,
            "berth_id": call.berth_id,
            "nodes": [
                {
                    **step.model_dump(mode="json"),
                    "resource": (
                        resources[step.resource_id].model_dump(mode="json")
                        if step.resource_id in resources
                        else None
                    ),
                }
                for step in steps
            ],
            "edges": [
                {"from": dep, "to": step.id}
                for step in steps
                for dep in step.dependency_step_ids
            ],
        }


    def _berth_compatible(self, call: PortCall, berth: Berth) -> bool:
        if berth.status == BerthStatus.MAINTENANCE:
            return False
        vessel = next((item for item in self.vessels if item.id == call.vessel_id), None)
        if vessel is None:
            return False
        if "Container" in vessel.vessel_type:
            return "Container" in berth.terminal
        if "tanker" in vessel.vessel_type.lower():
            return "Liquid" in berth.terminal
        return True

    def _berth_free_for_call(self, berth_id: str, target: PortCall) -> bool:
        for other in self.port_calls:
            if other.id == target.id or other.berth_id != berth_id:
                continue
            if target.arrival_eta < other.departure_eta and other.arrival_eta < target.departure_eta:
                return False
        return True

    def _resource_shift_needed(
        self,
        target_call_id: str,
        kind: ServiceKind,
        resource_id: str,
        separation_minutes: int = 45,
    ) -> int:
        target = next(
            (
                step for step in self.service_steps
                if step.port_call_id == target_call_id and step.kind == kind
            ),
            None,
        )
        resource = next(
            (
                item for item in self.service_resources
                if item.id == resource_id and item.kind == kind
            ),
            None,
        )
        if target is None or resource is None:
            return 0

        proposed = target.planned_at
        if resource.available_from and proposed < resource.available_from:
            proposed = resource.available_from

        separation = timedelta(minutes=separation_minutes)
        other_steps = sorted(
            [
                step for step in self.service_steps
                if step.port_call_id != target_call_id
                and step.kind == kind
                and step.resource_id == resource_id
            ],
            key=lambda item: item.planned_at,
        )

        # Capacity is modeled as the number of concurrent assignments permitted
        # inside the synthetic separation window.
        for _ in range(max(1, len(other_steps) + 2)):
            conflicts = [
                step for step in other_steps
                if abs((proposed - step.planned_at).total_seconds()) < separation.total_seconds()
            ]
            if len(conflicts) < max(resource.capacity, 1):
                break
            proposed = max(step.planned_at for step in conflicts) + separation

        return max(0, int((proposed - target.planned_at).total_seconds() // 60))

    def _apply_recovery_action(self, action: RecoveryAction) -> None:
        call = self._find_call(action.port_call_id, action.port_call_id)

        if action.action_type == RecoveryActionType.REASSIGN_RESOURCE:
            if action.service_kind is None or action.to_resource_id is None:
                raise ValueError("Resource reassignment requires service_kind and to_resource_id")

            step = next(
                (
                    item for item in self.service_steps
                    if item.port_call_id == call.id and item.kind == action.service_kind
                ),
                None,
            )
            target_resource = next(
                (
                    item for item in self.service_resources
                    if item.id == action.to_resource_id and item.kind == action.service_kind
                ),
                None,
            )
            if step is None or target_resource is None:
                raise ValueError("Recovery resource or service step is no longer available")

            old_resource = next(
                (item for item in self.service_resources if item.id == step.resource_id),
                None,
            )
            if old_resource and call.id in old_resource.assigned_port_call_ids:
                old_resource.assigned_port_call_ids.remove(call.id)

            if call.id not in target_resource.assigned_port_call_ids:
                target_resource.assigned_port_call_ids.append(call.id)
            step.resource_id = target_resource.id

        elif action.action_type == RecoveryActionType.MOVE_BERTH:
            if action.to_berth_id is None:
                raise ValueError("Berth move requires to_berth_id")

            new_berth = next(
                (item for item in self.berths if item.id == action.to_berth_id),
                None,
            )
            if new_berth is None or not self._berth_compatible(call, new_berth):
                raise ValueError("Recovery berth is unavailable or incompatible")

            old_berth_id = call.berth_id
            call.berth_id = new_berth.id

            vessel = next((item for item in self.vessels if item.id == call.vessel_id), None)
            if vessel:
                vessel.assigned_berth_id = new_berth.id

            berth_step = next(
                (
                    item for item in self.service_steps
                    if item.port_call_id == call.id and item.kind == ServiceKind.BERTH
                ),
                None,
            )
            if berth_step:
                berth_step.resource_id = new_berth.id

            old_berth_resource = next(
                (item for item in self.service_resources if item.id == old_berth_id),
                None,
            )
            new_berth_resource = next(
                (item for item in self.service_resources if item.id == new_berth.id),
                None,
            )
            if old_berth_resource and call.id in old_berth_resource.assigned_port_call_ids:
                old_berth_resource.assigned_port_call_ids.remove(call.id)
            if new_berth_resource and call.id not in new_berth_resource.assigned_port_call_ids:
                new_berth_resource.assigned_port_call_ids.append(call.id)

            crane_step = next(
                (
                    item for item in self.service_steps
                    if item.port_call_id == call.id and item.kind == ServiceKind.CRANE
                ),
                None,
            )
            if crane_step:
                old_crane = next(
                    (item for item in self.service_resources if item.id == crane_step.resource_id),
                    None,
                )
                new_crane_id = "crane-" + new_berth.id.replace("-", "") + "-a"
                new_crane = next(
                    (item for item in self.service_resources if item.id == new_crane_id),
                    None,
                )
                if old_crane and call.id in old_crane.assigned_port_call_ids:
                    old_crane.assigned_port_call_ids.remove(call.id)
                if new_crane:
                    if call.id not in new_crane.assigned_port_call_ids:
                        new_crane.assigned_port_call_ids.append(call.id)
                    crane_step.resource_id = new_crane.id

        elif action.action_type == RecoveryActionType.SHIFT_WINDOW:
            if action.shift_minutes <= 0:
                return
            stage_by_kind = {
                ServiceKind.PILOT: "pilot",
                ServiceKind.TUG: "tug",
                ServiceKind.BERTH: "berth",
                ServiceKind.CRANE: "cargo",
                ServiceKind.CARGO: "cargo",
                ServiceKind.BUNKER: "services",
                ServiceKind.STORES: "services",
                ServiceKind.DOCUMENTS: "services",
                ServiceKind.CUSTOMS: "departure",
                ServiceKind.GATE: "departure",
                ServiceKind.DEPARTURE: "departure",
            }
            stage_code = stage_by_kind.get(action.service_kind or ServiceKind.BERTH, "berth")
            shift_call_from_stage(call, stage_code, action.shift_minutes)

        else:
            raise ValueError(f"Unsupported recovery action: {action.action_type}")

    def _apply_recovery_actions(self, actions: list[RecoveryAction]) -> None:
        for action in actions:
            self._apply_recovery_action(action)
        self._recalculate_services()
        self._recalculate_risks()

    def _recovery_metrics(self, call_id: str) -> dict:
        self._recalculate_services()
        self._recalculate_risks()
        target = self._find_call(call_id, call_id)
        total_delay = int(sum(max(0, call.delay_minutes) for call in self.port_calls))
        blocked = sum(
            1 for step in self.service_steps
            if step.state == ServiceState.BLOCKED
        )
        conflicts = len(detect_berth_conflicts(self.port_calls))
        modeled_cost = float(total_delay * 720)
        disruption_score = float(
            total_delay
            + conflicts * 240
            + blocked * 60
        )
        return {
            "total_delay": total_delay,
            "blocked": blocked,
            "conflicts": conflicts,
            "modeled_cost": modeled_cost,
            "risk": target.risk,
            "disruption_score": disruption_score,
        }

    def _recovery_state_fingerprint(self, target_call_id: str) -> str:
        relevant = {
            "target_call_id": target_call_id,
            "port_calls": [
                {
                    "id": call.id,
                    "berth_id": call.berth_id,
                    "arrival_eta": call.arrival_eta.isoformat(),
                    "departure_eta": call.departure_eta.isoformat(),
                    "delay_minutes": call.delay_minutes,
                }
                for call in sorted(self.port_calls, key=lambda item: item.id)
            ],
            "active_incidents": [
                {
                    "id": incident.id,
                    "type": incident.incident_type.value,
                    "status": incident.status.value,
                    "target_port_call_id": incident.target_port_call_id,
                    "target_berth_id": incident.target_berth_id,
                    "target_resource_id": incident.target_resource_id,
                    "impact_minutes": incident.impact_minutes,
                }
                for incident in sorted(self.incidents, key=lambda item: item.id)
                if incident.status == IncidentStatus.ACTIVE
            ],
            "resources": [
                {
                    "id": resource.id,
                    "status": resource.status.value,
                    "capacity": resource.capacity,
                    "available_from": resource.available_from.isoformat() if resource.available_from else None,
                    "assigned_port_call_ids": sorted(resource.assigned_port_call_ids),
                }
                for resource in sorted(self.service_resources, key=lambda item: item.id)
            ],
            "weather_restriction": {
                "active": self.weather.restriction_active,
                "reason": self.weather.restriction_reason,
            },
        }
        payload = json.dumps(relevant, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _proposal_id(
        self,
        actions: list[RecoveryAction],
        target_call_id: str,
        state_fingerprint: str,
    ) -> str:
        payload = json.dumps(
            {
                "target_call_id": target_call_id,
                "state_fingerprint": state_fingerprint,
                "actions": [action.model_dump(mode="json") for action in actions],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "rec-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:14]

    def _project_recovery(
        self,
        title: str,
        target_call_id: str,
        actions: list[RecoveryAction],
        rationale: list[str],
        incident_id: str | None = None,
    ) -> RecoveryProposal:
        clone = HarborSimulator(initial=self.overview())
        clone._apply_recovery_actions(actions)
        metrics = clone._recovery_metrics(target_call_id)
        action_penalty = 5 * len(actions)
        metrics["disruption_score"] += action_penalty

        state_fingerprint = self._recovery_state_fingerprint(target_call_id)

        return RecoveryProposal(
            id=self._proposal_id(actions, target_call_id, state_fingerprint),
            state_fingerprint=state_fingerprint,
            title=title,
            target_port_call_id=target_call_id,
            incident_id=incident_id,
            actions=actions,
            projected_total_delay_minutes=metrics["total_delay"],
            projected_modeled_cost_usd=metrics["modeled_cost"],
            projected_berth_conflicts=metrics["conflicts"],
            projected_blocked_services=metrics["blocked"],
            projected_risk=metrics["risk"],
            disruption_score=metrics["disruption_score"],
            rationale=rationale,
            assumptions=[
                "Delay exposure is modeled at USD 720 per delay minute for this synthetic demo.",
                "Disruption score adds 240 points per berth conflict and 60 per blocked service.",
                "Resource feasibility respects available_from, capacity, and service-specific operating windows.",
                "Proposal output is decision support and requires explicit operator approval.",
            ],
            requires_approval=True,
        )

    def generate_recovery_proposals(
        self,
        call_id: str | None = None,
    ) -> list[RecoveryProposal]:
        proposals: list[RecoveryProposal] = []

        # Compound recovery for unavailable shared service resources.
        resource_failure_kinds = {
            IncidentType.TUG_UNAVAILABLE: (ServiceKind.TUG, 45),
            IncidentType.BUNKER_UNAVAILABLE: (ServiceKind.BUNKER, 60),
        }

        for incident in self.incidents:
            recovery_spec = resource_failure_kinds.get(incident.incident_type)
            if (
                incident.status != IncidentStatus.ACTIVE
                or recovery_spec is None
                or not incident.target_port_call_id
                or not incident.target_resource_id
            ):
                continue

            affected_kind, separation_minutes = recovery_spec
            target_call_id = incident.target_port_call_id
            if call_id and target_call_id != call_id:
                continue

            affected_steps = sorted(
                [
                    step for step in self.service_steps
                    if step.kind == affected_kind
                    and step.resource_id == incident.target_resource_id
                ],
                key=lambda item: item.planned_at,
            )
            if not affected_steps:
                continue

            alternatives = [
                resource for resource in self.service_resources
                if resource.kind == affected_kind
                and resource.id != incident.target_resource_id
                and resource.status != ResourceStatus.UNAVAILABLE
            ]

            for resource in alternatives:
                working = HarborSimulator(initial=self.overview())
                actions: list[RecoveryAction] = []
                rationale = [
                    (
                        f"{incident.target_resource_id} is unavailable for "
                        f"{len(affected_steps)} modeled {affected_kind.value} assignment(s)."
                    ),
                    (
                        f"Move the affected {affected_kind.value} workload to "
                        f"{resource.name} instead of recovering only one vessel."
                    ),
                ]

                for affected_step in affected_steps:
                    working_step = next(
                        (
                            step for step in working.service_steps
                            if step.port_call_id == affected_step.port_call_id
                            and step.kind == affected_kind
                        ),
                        None,
                    )
                    if working_step is None:
                        continue

                    reassign = RecoveryAction(
                        action_type=RecoveryActionType.REASSIGN_RESOURCE,
                        port_call_id=affected_step.port_call_id,
                        service_kind=affected_kind,
                        from_resource_id=working_step.resource_id,
                        to_resource_id=resource.id,
                    )
                    working._apply_recovery_actions([reassign])
                    actions.append(reassign)

                    shift = working._resource_shift_needed(
                        affected_step.port_call_id,
                        affected_kind,
                        resource.id,
                        separation_minutes=separation_minutes,
                    )
                    if shift:
                        if (
                            resource.available_from
                            and working_step.planned_at < resource.available_from
                        ):
                            rationale.append(
                                (
                                    f"{resource.name} becomes available at "
                                    f"{resource.available_from.isoformat()}."
                                )
                            )
                        shift_action = RecoveryAction(
                            action_type=RecoveryActionType.SHIFT_WINDOW,
                            port_call_id=affected_step.port_call_id,
                            service_kind=affected_kind,
                            shift_minutes=shift,
                        )
                        working._apply_recovery_actions([shift_action])
                        actions.append(shift_action)
                        rationale.append(
                            (
                                f"Shift {affected_step.port_call_id} by {shift} min "
                                f"to preserve the synthetic {separation_minutes}-minute "
                                f"{affected_kind.value} separation."
                            )
                        )
                    else:
                        rationale.append(
                            (
                                f"{affected_step.port_call_id} fits {resource.name}'s "
                                "current synthetic operating window."
                            )
                        )

                if actions:
                    proposals.append(
                        self._project_recovery(
                            title=(
                                f"Recover {incident.target_resource_id} workload "
                                f"with {resource.name}"
                            ),
                            target_call_id=target_call_id,
                            actions=actions,
                            rationale=rationale,
                            incident_id=incident.id,
                        )
                    )

        # Berth conflict recovery.
        for conflict in detect_berth_conflicts(self.port_calls):
            target_call_id = conflict.second_call_id
            if call_id and target_call_id != call_id:
                continue
            target = self._find_call(target_call_id, target_call_id)
            related_incident = next(
                (
                    incident for incident in self.incidents
                    if incident.status == IncidentStatus.ACTIVE
                    and incident.target_berth_id == conflict.berth_id
                ),
                None,
            )

            candidate_berths = [
                berth for berth in self.berths
                if berth.id != target.berth_id
                and self._berth_compatible(target, berth)
                and self._berth_free_for_call(berth.id, target)
            ]

            for berth in candidate_berths[:2]:
                actions = [
                    RecoveryAction(
                        action_type=RecoveryActionType.MOVE_BERTH,
                        port_call_id=target.id,
                        service_kind=ServiceKind.BERTH,
                        from_berth_id=target.berth_id,
                        to_berth_id=berth.id,
                    )
                ]
                proposals.append(
                    self._project_recovery(
                        title=f"Move {target.id} to {berth.name}",
                        target_call_id=target.id,
                        actions=actions,
                        rationale=[
                            f"{target.berth_id} has a {conflict.overlap_minutes}-minute modeled overlap.",
                            f"{berth.name} is compatible with the synthetic vessel/terminal rules and is clear for the modeled window.",
                            "Move the berth assignment while preserving the current arrival window.",
                        ],
                        incident_id=related_incident.id if related_incident else None,
                    )
                )

            shift = conflict.overlap_minutes + 15
            actions = [
                RecoveryAction(
                    action_type=RecoveryActionType.SHIFT_WINDOW,
                    port_call_id=target.id,
                    service_kind=ServiceKind.BERTH,
                    shift_minutes=shift,
                )
            ]
            proposals.append(
                self._project_recovery(
                    title=f"Hold {target.id} for {shift} min",
                    target_call_id=target.id,
                    actions=actions,
                    rationale=[
                        f"Wait for {conflict.berth_id} to clear its {conflict.overlap_minutes}-minute overlap.",
                        "Add a 15-minute synthetic operating buffer before the next berth window.",
                    ],
                    incident_id=related_incident.id if related_incident else None,
                )
            )

        unique: dict[str, RecoveryProposal] = {}
        for proposal in proposals:
            unique[proposal.id] = proposal

        return sorted(
            unique.values(),
            key=lambda proposal: (
                proposal.disruption_score,
                proposal.projected_modeled_cost_usd,
                proposal.id,
            ),
        )

    def apply_recovery_proposal(
        self,
        proposal_id: str,
        approved_by: str,
        approved_role: OperatorRole,
        approved_display_name: str | None = None,
    ) -> RecoveryApplicationReceipt:
        if approved_role not in {OperatorRole.OPERATOR, OperatorRole.SUPERVISOR}:
            raise ValueError("Operator or supervisor role required for recovery approval")
        if not approved_by.strip():
            raise ValueError("Recovery approval requires a non-empty operator identity")

        proposal = next(
            (
                item for item in self.generate_recovery_proposals()
                if item.id == proposal_id
            ),
            None,
        )
        if proposal is None:
            raise ValueError("Recovery proposal is stale, unavailable, or already applied")

        self._apply_recovery_actions(proposal.actions)
        metrics = self._recovery_metrics(proposal.target_port_call_id)

        receipt = RecoveryApplicationReceipt(
            proposal_id=proposal.id,
            state_fingerprint=proposal.state_fingerprint,
            applied_at=datetime.now(timezone.utc).replace(microsecond=0),
            target_port_call_id=proposal.target_port_call_id,
            actions=proposal.actions,
            resulting_berth_conflicts=metrics["conflicts"],
            resulting_blocked_services=metrics["blocked"],
            resulting_total_delay_minutes=metrics["total_delay"],
            resulting_modeled_cost_usd=metrics["modeled_cost"],
            approved_by=approved_by,
            approved_role=approved_role,
            approved_display_name=approved_display_name,
        )

        if self.recovery_receipt_sink:
            stored = self.recovery_receipt_sink(receipt)
            if not stored:
                raise ValueError("Recovery proposal receipt already exists")

        self._emit(
            "recovery",
            RiskLevel.LOW if metrics["conflicts"] == 0 and metrics["blocked"] == 0 else RiskLevel.MEDIUM,
            f"Recovery applied: {proposal.title}",
            (
                f"Approved recovery proposal {proposal.id}; "
                f"{metrics['conflicts']} conflict(s), {metrics['blocked']} blocked service(s), "
                f"{metrics['total_delay']} total modeled delay minutes remain."
            ),
            port_call_id=proposal.target_port_call_id,
            incident_id=proposal.incident_id,
        )
        self._persist()
        return receipt

    def _emit(self, category: str, severity: RiskLevel, title: str, message: str, **refs) -> OperationsEvent:
        event = OperationsEvent(
            id=f"evt-{uuid4().hex[:14]}",
            occurred_at=datetime.now(timezone.utc).replace(microsecond=0),
            category=category,
            severity=severity,
            title=title,
            message=message,
            **refs,
        )
        self.events.insert(0, event)
        self.events = self.events[:50]

        if self.event_sink:
            self.event_sink(event)

        if self.connectivity.mode == LinkMode.OFFLINE_EDGE and self.spool_sink:
            self.spool_sink(event)
            self._refresh_queued_count()

        return event

    def _refresh_queued_count(self) -> None:
        if self.pending_count:
            self.connectivity.queued_events = self.pending_count()

    def _persist(self) -> None:
        if self.snapshot_sink:
            self.snapshot_sink(self.overview())

    def _find_call(self, call_id: str | None, fallback: str) -> PortCall:
        wanted = call_id or fallback
        call = next((item for item in self.port_calls if item.id == wanted), None)
        if call is None:
            raise ValueError(f"Unknown port call: {wanted}")
        return call

    def _recalculate_risks(self) -> None:
        conflicts = detect_berth_conflicts(self.port_calls)
        conflicted_ids = {c.first_call_id for c in conflicts} | {c.second_call_id for c in conflicts}
        for call in self.port_calls:
            level, _, _ = score_port_call(call, self.weather, call.id in conflicted_ids)
            call.risk = level
            call.estimated_cost_exposure_usd = max(
                call.estimated_cost_exposure_usd,
                call.delay_minutes * 720,
            )

    def set_connectivity(self, mode: LinkMode) -> None:
        previous = self.connectivity.mode
        now = datetime.now(timezone.utc).replace(microsecond=0)

        if mode == LinkMode.FULL:
            self.connectivity = ConnectivityState(
                mode=mode,
                primary_link="Fiber / LTE",
                fallback_link="Satellite",
                bandwidth_kbps=50000,
                queued_events=self.connectivity.queued_events,
                last_transition_at=now,
            )
        elif mode == LinkMode.DEGRADED:
            self.connectivity = ConnectivityState(
                mode=mode,
                primary_link="Satellite broadband",
                fallback_link="Narrowband",
                bandwidth_kbps=2500,
                queued_events=self.connectivity.queued_events,
                last_transition_at=now,
            )
        elif mode == LinkMode.CRITICAL:
            self.connectivity = ConnectivityState(
                mode=mode,
                primary_link="Narrowband satellite",
                fallback_link=None,
                bandwidth_kbps=10,
                queued_events=self.connectivity.queued_events,
                last_transition_at=now,
            )
        else:
            self.connectivity = ConnectivityState(
                mode=mode,
                primary_link="Local edge only",
                fallback_link=None,
                bandwidth_kbps=0,
                queued_events=self.connectivity.queued_events,
                last_transition_at=now,
            )

        replayed = 0
        if mode == LinkMode.FULL and previous == LinkMode.OFFLINE_EDGE and self.replay_sink:
            replayed = self.replay_sink()
            self._refresh_queued_count()

        self._emit(
            "connectivity",
            RiskLevel.HIGH if mode != LinkMode.FULL else RiskLevel.LOW,
            f"Connectivity mode: {mode.value}",
            (
                f"Transport restored; {replayed} queued event(s) replayed and acknowledged."
                if replayed
                else "Transport policy changed; local operations state remains available."
            ),
        )
        self._refresh_queued_count()
        self._persist()

    def inject_incident(
        self,
        incident_type: IncidentType,
        target_port_call_id: str | None = None,
        impact_minutes: int | None = None,
    ) -> Incident:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        incident_id = f"inc-{uuid4().hex[:12]}"

        target_resource_id: str | None = None

        if incident_type == IncidentType.PILOT_DELAY:
            call = self._find_call(target_port_call_id, "pc-aurora")
            pilot_step = next(
                (step for step in self.service_steps if step.port_call_id == call.id and step.kind == ServiceKind.PILOT),
                None,
            )
            target_resource_id = pilot_step.resource_id if pilot_step else None
            impact = impact_minutes or 25
            shift_call_from_stage(call, "pilot", impact)
            severity = RiskLevel.HIGH
            title = "Pilot boarding delay"
            details = f"{call.id} pilot sequence shifted by {impact} min."
            berth_id = call.berth_id

        elif incident_type == IncidentType.TUG_UNAVAILABLE:
            call = self._find_call(target_port_call_id, "pc-aurora")
            tug_step = next(
                (step for step in self.service_steps if step.port_call_id == call.id and step.kind == ServiceKind.TUG),
                None,
            )
            target_resource_id = tug_step.resource_id if tug_step else None
            impact = impact_minutes or 40
            shift_call_from_stage(call, "tug", impact)
            severity = RiskLevel.HIGH
            title = "Assigned tug unavailable"
            details = f"{call.id} maneuvering and berth sequence shifted by {impact} min."
            berth_id = call.berth_id

        elif incident_type == IncidentType.BUNKER_UNAVAILABLE:
            call = self._find_call(target_port_call_id, "pc-aurora")
            bunker_step = next(
                (
                    step for step in self.service_steps
                    if step.port_call_id == call.id
                    and step.kind == ServiceKind.BUNKER
                ),
                None,
            )
            target_resource_id = bunker_step.resource_id if bunker_step else None
            impact = impact_minutes or 45
            shift_call_from_stage(call, "services", impact)
            severity = RiskLevel.HIGH
            title = "Assigned bunker barge unavailable"
            details = (
                f"{call.id} bunker service and dependent departure sequence "
                f"shifted by {impact} min."
            )
            berth_id = call.berth_id

        elif incident_type == IncidentType.BERTH_OVERRUN:
            call = self._find_call(target_port_call_id, "pc-glory")
            target_resource_id = call.berth_id
            impact = impact_minutes or 90
            extend_departure(call, impact)
            severity = RiskLevel.CRITICAL
            title = "Berth occupation overrun"
            details = f"{call.berth_id} occupation extended by {impact} min; downstream berth windows recalculated."
            berth_id = call.berth_id

        elif incident_type == IncidentType.WIND_RESTRICTION:
            call = None
            impact = impact_minutes or 30
            self.weather.gust_knots = max(self.weather.gust_knots, 36)
            self.weather.restriction_active = True
            self.weather.restriction_reason = "High-wind pilot/tug restriction"
            for candidate in self.port_calls:
                vessel = next((v for v in self.vessels if v.id == candidate.vessel_id), None)
                if vessel and vessel.status in {
                    VesselStatus.INBOUND,
                    VesselStatus.AT_ANCHOR,
                    VesselStatus.MANEUVERING,
                }:
                    shift_call_from_stage(candidate, "pilot", impact)
            severity = RiskLevel.CRITICAL
            title = "High-wind movement restriction"
            details = f"Inbound pilot/tug movements shifted by {impact} min."
            berth_id = None

        elif incident_type == IncidentType.CONNECTIVITY_LOSS:
            call = None
            impact = 0
            self.set_connectivity(LinkMode.OFFLINE_EDGE)
            severity = RiskLevel.HIGH
            title = "Control-center link lost"
            details = "PortFlow switched to local edge mode; outbound events are durably spooled."
            berth_id = None

        else:
            raise ValueError(f"Unsupported incident type: {incident_type}")

        incident = Incident(
            id=incident_id,
            incident_type=incident_type,
            severity=severity,
            title=title,
            started_at=now,
            target_port_call_id=call.id if call else target_port_call_id,
            target_berth_id=berth_id,
            target_resource_id=target_resource_id,
            impact_minutes=impact,
            details=details,
        )
        self.incidents.insert(0, incident)

        if self.incident_sink:
            self.incident_sink(incident)

        self._recalculate_risks()
        self._recalculate_services()
        self._emit(
            "incident",
            severity,
            title,
            details,
            port_call_id=incident.target_port_call_id,
            berth_id=incident.target_berth_id,
            incident_id=incident.id,
        )
        self._persist()
        return incident

    def resolve_incident(self, incident_id: str) -> Incident:
        incident = next((item for item in self.incidents if item.id == incident_id), None)
        if incident is None:
            raise ValueError(f"Unknown incident: {incident_id}")

        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = datetime.now(timezone.utc).replace(microsecond=0)

        if self.incident_sink:
            self.incident_sink(incident)

        self._recalculate_services()
        self._emit(
            "incident",
            RiskLevel.LOW,
            f"Resolved: {incident.title}",
            "Incident closed; prior timeline changes remain in the audit trail.",
            incident_id=incident.id,
            port_call_id=incident.target_port_call_id,
            berth_id=incident.target_berth_id,
        )
        self._persist()
        return incident

    def tick(self) -> None:
        self.tick_count += 1
        now = datetime.now(timezone.utc).replace(microsecond=0)

        for vessel in self.vessels:
            if vessel.source_id != "synthetic-ais":
                continue
            if vessel.status in {
                VesselStatus.INBOUND,
                VesselStatus.MANEUVERING,
                VesselStatus.OUTBOUND,
            }:
                distance = max(vessel.speed_knots, 0.5) * 0.000018
                rad = math.radians(vessel.heading_deg)
                vessel.position.lat += math.cos(rad) * distance
                vessel.position.lon += math.sin(rad) * distance

        if self.weather.source_id == "synthetic-weather":
            wind_incident = any(
                incident.status == IncidentStatus.ACTIVE
                and incident.incident_type == IncidentType.WIND_RESTRICTION
                for incident in self.incidents
            )
            self.weather.observed_at = now
            if not wind_incident:
                self.weather.wind_knots = round(18 + 4 * math.sin(self.tick_count / 7), 1)
                self.weather.gust_knots = round(self.weather.wind_knots + 7.5, 1)
                self.weather.restriction_active = self.weather.gust_knots >= 33
                self.weather.restriction_reason = (
                    "High-wind pilot/tug restriction"
                    if self.weather.restriction_active
                    else None
                )

            self.weather.wave_height_m = round(1.1 + 0.3 * math.sin(self.tick_count / 5), 1)
            self.weather.tide_m = round(0.8 + 0.5 * math.sin(self.tick_count / 14), 2)

        self._refresh_queued_count()
        self._recalculate_risks()
        self._recalculate_services()

        if self.tick_count % 12 == 0:
            aurora = self._find_call("pc-aurora", "pc-aurora")
            self._emit(
                "port_call",
                aurora.risk,
                "MSC Aurora critical path refreshed",
                f"Modeled delay {aurora.delay_minutes} min; exposure USD {aurora.estimated_cost_exposure_usd:,.0f}.",
                vessel_id="v-aurora",
                berth_id="b-12",
                port_call_id="pc-aurora",
            )

        if self.tick_count % 3 == 0:
            self._persist()

    def _data_disclaimer(self) -> str:
        modes = {source.mode for source in self.data_sources}
        if DataSourceMode.LIVE in modes and DataSourceMode.RECORDED in modes:
            return (
                "Demonstration only. Current harbor state includes explicitly labeled live adapter data "
                "and recorded fixture replays alongside synthetic operational data."
            )
        if DataSourceMode.LIVE in modes:
            return (
                "Demonstration only. Current harbor state includes explicitly labeled live adapter data "
                "alongside synthetic operational data."
            )
        if DataSourceMode.RECORDED in modes:
            return (
                "Demonstration only. No live external feeds are active. Current harbor state includes "
                "explicitly labeled recorded fixture replays alongside synthetic operational data."
            )
        return (
            "Demonstration only. No live external feeds are active. Vessel, port-call, weather, risk, "
            "incident, service, and operational data are synthetic."
        )

    def overview(self) -> HarborOverview:
        self._refresh_data_source_freshness()
        occupied = sum(1 for berth in self.berths if berth.status == BerthStatus.OCCUPIED)
        at_risk = sum(
            1 for call in self.port_calls
            if call.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        )
        avg_delay = round(
            sum(call.delay_minutes for call in self.port_calls) / max(len(self.port_calls), 1),
            1,
        )
        blocked_services = sum(
            1 for step in self.service_steps
            if step.state == ServiceState.BLOCKED
        )
        delayed_services = sum(
            1 for step in self.service_steps
            if step.state == ServiceState.DELAYED
        )

        return HarborOverview(
            generated_at=datetime.now(timezone.utc).replace(microsecond=0),
            port_name=self.port_name,
            center=self.center,
            vessels=deepcopy(self.vessels),
            berths=deepcopy(self.berths),
            port_calls=deepcopy(self.port_calls),
            weather=deepcopy(self.weather),
            connectivity=deepcopy(self.connectivity),
            incidents=deepcopy(self.incidents),
            service_resources=deepcopy(self.service_resources),
            service_steps=deepcopy(self.service_steps),
            events=deepcopy(self.events),
            data_sources=deepcopy(self.data_sources),
            metrics={
                "vessels_in_port_picture": len(self.vessels),
                "berths_occupied": occupied,
                "berths_total": len(self.berths),
                "port_calls_at_risk": at_risk,
                "average_delay_minutes": avg_delay,
                "active_incidents": sum(
                    1 for incident in self.incidents
                    if incident.status == IncidentStatus.ACTIVE
                ),
                "berth_conflicts": len(detect_berth_conflicts(self.port_calls)),
                "blocked_services": blocked_services,
                "delayed_services": delayed_services,
                "queued_events": self.connectivity.queued_events,
                "stale_data_sources": sum(
                    1 for source in self.data_sources if source.stale
                ),
            },
            data_disclaimer=self._data_disclaimer(),
        )
