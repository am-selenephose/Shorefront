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
    PortCall, PortCallStage, RiskLevel, Vessel, VesselStatus, WeatherState,
)


EventSink = Callable[[OperationsEvent], None]
IncidentSink = Callable[[Incident], None]
SnapshotSink = Callable[[HarborOverview], None]


class HarborSimulator:
    def __init__(
        self,
        seed: int = 42,
        initial: HarborOverview | None = None,
        event_sink: EventSink | None = None,
        incident_sink: IncidentSink | None = None,
        snapshot_sink: SnapshotSink | None = None,
    ):
        self.rng = random.Random(seed)
        self.event_sink = event_sink
        self.incident_sink = incident_sink
        self.snapshot_sink = snapshot_sink
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
            wind_knots=19.0, gust_knots=26.0, visibility_km=9.4,
            wave_height_m=1.2, tide_m=0.8, restriction_active=False,
        )
        self.connectivity = ConnectivityState(
            mode=LinkMode.FULL, primary_link="Fiber / LTE", fallback_link="Satellite",
            bandwidth_kbps=50000, queued_events=0, last_transition_at=self._started,
        )
        self.incidents: list[Incident] = []
        self.events: list[OperationsEvent] = []
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
        self.events = deepcopy(state.events)

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
            PortCallStage(code=c, label=l, planned_at=arrival+timedelta(minutes=m), dependency_codes=d)
            for c, l, m, d in specs
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

    def _emit(self, category: str, severity: RiskLevel, title: str, message: str, **refs) -> OperationsEvent:
        event = OperationsEvent(
            id=f"evt-{uuid4().hex[:14]}",
            occurred_at=datetime.now(timezone.utc).replace(microsecond=0),
            category=category, severity=severity, title=title, message=message, **refs,
        )
        self.events.insert(0, event)
        self.events = self.events[:50]
        if self.event_sink:
            self.event_sink(event)
        return event

    def _persist(self) -> None:
        if self.snapshot_sink:
            self.snapshot_sink(self.overview())

    def _find_call(self, call_id: str | None, fallback: str) -> PortCall:
        wanted = call_id or fallback
        call = next((p for p in self.port_calls if p.id == wanted), None)
        if call is None:
            raise ValueError(f"Unknown port call: {wanted}")
        return call

    def _recalculate_risks(self) -> None:
        conflicts = detect_berth_conflicts(self.port_calls)
        conflicted_ids = {c.first_call_id for c in conflicts} | {c.second_call_id for c in conflicts}
        for call in self.port_calls:
            level, _, _ = score_port_call(call, self.weather, call.id in conflicted_ids)
            call.risk = level
            call.estimated_cost_exposure_usd = max(call.estimated_cost_exposure_usd, call.delay_minutes * 720)

    def set_connectivity(self, mode: LinkMode) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        queued = self.connectivity.queued_events
        if mode == LinkMode.FULL:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Fiber / LTE", fallback_link="Satellite",
                                                  bandwidth_kbps=50000, queued_events=0, last_transition_at=now)
        elif mode == LinkMode.DEGRADED:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Satellite broadband", fallback_link="Narrowband",
                                                  bandwidth_kbps=2500, queued_events=queued, last_transition_at=now)
        elif mode == LinkMode.CRITICAL:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Narrowband satellite", fallback_link=None,
                                                  bandwidth_kbps=10, queued_events=queued, last_transition_at=now)
        else:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Local edge only", fallback_link=None,
                                                  bandwidth_kbps=0, queued_events=queued, last_transition_at=now)
        self._emit("connectivity", RiskLevel.HIGH if mode != LinkMode.FULL else RiskLevel.LOW,
                   f"Connectivity mode: {mode.value}",
                   "Transport policy changed; local operations state remains available.")
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
                if vessel and vessel.status in {VesselStatus.INBOUND, VesselStatus.AT_ANCHOR, VesselStatus.MANEUVERING}:
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
            details = "PortFlow switched to local edge mode; events will queue for replay."
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
        self._emit(
            "incident", severity, title, details,
            port_call_id=incident.target_port_call_id,
            berth_id=incident.target_berth_id,
            incident_id=incident.id,
        )
        self._persist()
        return incident

    def resolve_incident(self, incident_id: str) -> Incident:
        incident = next((x for x in self.incidents if x.id == incident_id), None)
        if incident is None:
            raise ValueError(f"Unknown incident: {incident_id}")
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = datetime.now(timezone.utc).replace(microsecond=0)
        if self.incident_sink:
            self.incident_sink(incident)
        self._emit("incident", RiskLevel.LOW, f"Resolved: {incident.title}",
                   "Incident closed; prior operational timeline changes remain part of the audit trail.",
                   incident_id=incident.id,
                   port_call_id=incident.target_port_call_id,
                   berth_id=incident.target_berth_id)
        self._persist()
        return incident

    def tick(self) -> None:
        self.tick_count += 1
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for vessel in self.vessels:
            if vessel.status in {VesselStatus.INBOUND, VesselStatus.MANEUVERING, VesselStatus.OUTBOUND}:
                distance = max(vessel.speed_knots, 0.5) * 0.000018
                rad = math.radians(vessel.heading_deg)
                vessel.position.lat += math.cos(rad) * distance
                vessel.position.lon += math.sin(rad) * distance

        wind_incident = any(
            x.status == IncidentStatus.ACTIVE and x.incident_type == IncidentType.WIND_RESTRICTION
            for x in self.incidents
        )
        self.weather.observed_at = now
        if not wind_incident:
            self.weather.wind_knots = round(18 + 4 * math.sin(self.tick_count / 7), 1)
            self.weather.gust_knots = round(self.weather.wind_knots + 7.5, 1)
            self.weather.restriction_active = self.weather.gust_knots >= 33
            self.weather.restriction_reason = "High-wind pilot/tug restriction" if self.weather.restriction_active else None
        self.weather.wave_height_m = round(1.1 + 0.3 * math.sin(self.tick_count / 5), 1)
        self.weather.tide_m = round(0.8 + 0.5 * math.sin(self.tick_count / 14), 2)

        if self.connectivity.mode == LinkMode.OFFLINE_EDGE:
            self.connectivity.queued_events += 1

        self._recalculate_risks()
        if self.tick_count % 12 == 0:
            aurora = self._find_call("pc-aurora", "pc-aurora")
            self._emit("port_call", aurora.risk, "MSC Aurora critical path refreshed",
                       f"Modeled delay {aurora.delay_minutes} min; exposure USD {aurora.estimated_cost_exposure_usd:,.0f}.",
                       vessel_id="v-aurora", berth_id="b-12", port_call_id="pc-aurora")
        if self.tick_count % 3 == 0:
            self._persist()

    def overview(self) -> HarborOverview:
        occupied = sum(1 for berth in self.berths if berth.status == BerthStatus.OCCUPIED)
        at_risk = sum(1 for call in self.port_calls if call.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL})
        avg_delay = round(sum(call.delay_minutes for call in self.port_calls) / max(len(self.port_calls), 1), 1)
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
            events=deepcopy(self.events),
            metrics={
                "vessels_in_port_picture": len(self.vessels),
                "berths_occupied": occupied,
                "berths_total": len(self.berths),
                "port_calls_at_risk": at_risk,
                "average_delay_minutes": avg_delay,
                "active_incidents": sum(1 for x in self.incidents if x.status == IncidentStatus.ACTIVE),
                "berth_conflicts": len(detect_berth_conflicts(self.port_calls)),
            },
            data_disclaimer="Demonstration only. Vessel, port-call, risk, incident, and operational data are synthetic.",
        )
