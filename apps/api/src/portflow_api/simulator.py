from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import random
from typing import Callable
from uuid import uuid4

from .domain import detect_berth_conflicts, extend_departure, score_port_call, shift_call_from_stage
from .models import (
    Berth, BerthStatus, ConnectivityState, Coordinate, HarborOverview,
    Incident, IncidentStatus, IncidentType, LinkMode, OperationsEvent,
    PortCall, PortCallStage, ResourceStatus, RiskLevel, ServiceKind,
    ServiceResource, ServiceState, ServiceStep, Vessel, VesselStatus, WeatherState,
)


EventSink = Callable[[OperationsEvent], None]
IncidentSink = Callable[[Incident], None]
SnapshotSink = Callable[[HarborOverview], None]
SpoolSink = Callable[[OperationsEvent], bool]
ReplaySink = Callable[[], int]
PendingCount = Callable[[], int]


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
    ):
        self.rng = random.Random(seed)
        self.event_sink = event_sink
        self.incident_sink = incident_sink
        self.snapshot_sink = snapshot_sink
        self.spool_sink = spool_sink
        self.replay_sink = replay_sink
        self.pending_count = pending_count
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
        self.service_resources = deepcopy(state.service_resources)
        self.service_steps = deepcopy(state.service_steps)
        self.events = deepcopy(state.events)

        # Backward-compatible restore for snapshots created before v0.3.
        if not self.service_resources:
            self.service_resources = self._make_service_resources()
        if not self.service_steps:
            self.service_steps = self._make_service_steps()

        self._refresh_queued_count()
        self._recalculate_services()
        self._recalculate_risks()

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
            specs = [
                (ServiceKind.PILOT, "Pilot boarding", self._stage_time(call, "pilot", call.arrival_eta), None),
                (ServiceKind.TUG, "Tug rendezvous", self._stage_time(call, "tug", call.arrival_eta), None),
                (ServiceKind.BERTH, "Berth access", self._stage_time(call, "berth", call.arrival_eta), call.berth_id),
                (ServiceKind.CRANE, "Crane allocation", self._stage_time(call, "cargo", call.arrival_eta), None),
                (ServiceKind.CARGO, "Cargo operation", self._stage_time(call, "cargo", call.arrival_eta)+timedelta(minutes=10), None),
                (ServiceKind.CUSTOMS, "Customs release", call.departure_eta-timedelta(minutes=60), None),
                (ServiceKind.DEPARTURE, "Departure clearance", call.departure_eta, None),
            ]
            previous_id: str | None = None
            for kind, label, planned_at, fixed_resource in specs:
                step_id = f"svc-{call.id}-{kind.value}"
                resource_id = fixed_resource if fixed_resource else self._resource_for(call, kind)
                steps.append(ServiceStep(
                    id=step_id,
                    port_call_id=call.id,
                    kind=kind,
                    label=label,
                    planned_at=planned_at,
                    state=ServiceState.ASSIGNED if resource_id else ServiceState.READY,
                    resource_id=resource_id,
                    dependency_step_ids=[previous_id] if previous_id else [],
                ))
                previous_id = step_id
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
            elif step.kind == ServiceKind.CUSTOMS:
                step.planned_at = call.departure_eta - timedelta(minutes=60)
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
            elif incident.incident_type == IncidentType.TUG_UNAVAILABLE and incident.target_port_call_id:
                self._mark_step(incident.target_port_call_id, ServiceKind.TUG, ServiceState.BLOCKED)
                self._mark_resource_for_call(incident.target_port_call_id, ServiceKind.TUG, ResourceStatus.UNAVAILABLE)
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

        if incident_type == IncidentType.PILOT_DELAY:
            call = self._find_call(target_port_call_id, "pc-aurora")
            impact = impact_minutes or 25
            shift_call_from_stage(call, "pilot", impact)
            severity = RiskLevel.HIGH
            title = "Pilot boarding delay"
            details = f"{call.id} pilot sequence shifted by {impact} min."
            berth_id = call.berth_id

        elif incident_type == IncidentType.TUG_UNAVAILABLE:
            call = self._find_call(target_port_call_id, "pc-aurora")
            impact = impact_minutes or 40
            shift_call_from_stage(call, "tug", impact)
            severity = RiskLevel.HIGH
            title = "Assigned tug unavailable"
            details = f"{call.id} maneuvering and berth sequence shifted by {impact} min."
            berth_id = call.berth_id

        elif incident_type == IncidentType.BERTH_OVERRUN:
            call = self._find_call(target_port_call_id, "pc-glory")
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
            if vessel.status in {
                VesselStatus.INBOUND,
                VesselStatus.MANEUVERING,
                VesselStatus.OUTBOUND,
            }:
                distance = max(vessel.speed_knots, 0.5) * 0.000018
                rad = math.radians(vessel.heading_deg)
                vessel.position.lat += math.cos(rad) * distance
                vessel.position.lon += math.sin(rad) * distance

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

    def overview(self) -> HarborOverview:
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
            },
            data_disclaimer=(
                "Demonstration only. Vessel, port-call, risk, incident, service, "
                "and operational data are synthetic."
            ),
        )
