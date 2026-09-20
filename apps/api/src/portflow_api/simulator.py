from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math, random
from .models import Berth, BerthStatus, ConnectivityState, Coordinate, HarborOverview, LinkMode, OperationsEvent, PortCall, PortCallStage, RiskLevel, Vessel, VesselStatus, WeatherState

class HarborSimulator:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.tick_count = 0
        self.port_name = "PortFlow Demo Harbor"
        self.center = Coordinate(lat=51.948, lon=4.142)
        self._started = datetime.now(timezone.utc).replace(microsecond=0)
        self.vessels = self._make_vessels()
        self.berths = self._make_berths()
        self.port_calls = self._make_port_calls()
        self.weather = WeatherState(observed_at=self._started, wind_knots=19.0, gust_knots=26.0, visibility_km=9.4, wave_height_m=1.2, tide_m=0.8, restriction_active=False)
        self.connectivity = ConnectivityState(mode=LinkMode.FULL, primary_link="Fiber / LTE", fallback_link="Satellite", bandwidth_kbps=50000, queued_events=0, last_transition_at=self._started)
        self.events: list[OperationsEvent] = []
        self._emit("system", RiskLevel.LOW, "Operations picture initialized", "Synthetic harbor state is live.")

    def _make_vessels(self):
        now = self._started
        return [
            Vessel(id="v-aurora", name="MSC Aurora", imo="9991001", vessel_type="Container", status=VesselStatus.INBOUND, position=Coordinate(lat=51.989, lon=3.970), speed_knots=11.8, heading_deg=92, eta=now+timedelta(minutes=54), assigned_berth_id="b-12", cargo_summary="8,420 TEU mixed container"),
            Vessel(id="v-lima", name="Maersk Lima", imo="9991002", vessel_type="Container", status=VesselStatus.AT_ANCHOR, position=Coordinate(lat=52.010, lon=3.910), speed_knots=0.2, heading_deg=180, eta=now+timedelta(minutes=88), assigned_berth_id="b-09", cargo_summary="6,100 TEU mixed container"),
            Vessel(id="v-glory", name="Ever Glory", imo="9991003", vessel_type="Container", status=VesselStatus.MANEUVERING, position=Coordinate(lat=51.963, lon=4.045), speed_knots=6.4, heading_deg=104, eta=now+timedelta(minutes=22), assigned_berth_id="b-07", cargo_summary="4,780 TEU"),
            Vessel(id="v-nordic", name="Nordic Atlas", imo="9991004", vessel_type="Product tanker", status=VesselStatus.BERTHED, position=Coordinate(lat=51.934, lon=4.155), speed_knots=0, heading_deg=0, assigned_berth_id="b-03", cargo_summary="Refined products"),
            Vessel(id="v-seaway", name="Seaway Polaris", imo="9991005", vessel_type="Ro-Ro", status=VesselStatus.OUTBOUND, position=Coordinate(lat=51.968, lon=4.010), speed_knots=9.2, heading_deg=274, cargo_summary="Vehicles / project cargo"),
        ]

    def _make_berths(self):
        return [
            Berth(id="b-03", name="Berth 03", terminal="Liquid Bulk", status=BerthStatus.OCCUPIED, max_length_m=310, position=Coordinate(lat=51.934, lon=4.155), vessel_id="v-nordic"),
            Berth(id="b-07", name="Berth 07", terminal="Delta Container", status=BerthStatus.RESERVED, max_length_m=400, position=Coordinate(lat=51.951, lon=4.133), vessel_id="v-glory"),
            Berth(id="b-09", name="Berth 09", terminal="Delta Container", status=BerthStatus.RESERVED, max_length_m=400, position=Coordinate(lat=51.947, lon=4.119), vessel_id="v-lima"),
            Berth(id="b-12", name="Berth 12", terminal="Maas Container", status=BerthStatus.RESERVED, max_length_m=420, position=Coordinate(lat=51.942, lon=4.101), vessel_id="v-aurora"),
            Berth(id="b-15", name="Berth 15", terminal="Maas Container", status=BerthStatus.AVAILABLE, max_length_m=420, position=Coordinate(lat=51.938, lon=4.083)),
        ]

    def _stages(self, arrival):
        specs = [
            ("notice", "Arrival notice accepted", -90, []), ("pilot", "Pilot ordered", -55, ["notice"]),
            ("pilot_board", "Pilot aboard", -35, ["pilot"]), ("tug", "Tug rendezvous", -22, ["pilot_board"]),
            ("berth", "All fast at berth", 0, ["tug"]), ("cargo", "Cargo operations", 35, ["berth"]),
            ("services", "Bunkers / stores / services", 70, ["berth"]), ("departure", "Departure clearance", 360, ["cargo", "services"]),
        ]
        return [PortCallStage(code=c, label=l, planned_at=arrival+timedelta(minutes=m), dependency_codes=d) for c,l,m,d in specs]

    def _make_port_calls(self):
        now = self._started
        return [
            PortCall(id="pc-aurora", vessel_id="v-aurora", berth_id="b-12", arrival_eta=now+timedelta(minutes=54), departure_eta=now+timedelta(hours=9), stages=self._stages(now+timedelta(minutes=54))),
            PortCall(id="pc-lima", vessel_id="v-lima", berth_id="b-09", arrival_eta=now+timedelta(minutes=88), departure_eta=now+timedelta(hours=11), stages=self._stages(now+timedelta(minutes=88))),
            PortCall(id="pc-glory", vessel_id="v-glory", berth_id="b-07", arrival_eta=now+timedelta(minutes=22), departure_eta=now+timedelta(hours=7), stages=self._stages(now+timedelta(minutes=22))),
        ]

    def _emit(self, category, severity, title, message, **refs):
        e = OperationsEvent(id=f"evt-{len(self.events)+1:04d}", occurred_at=datetime.now(timezone.utc).replace(microsecond=0), category=category, severity=severity, title=title, message=message, **refs)
        self.events.insert(0, e)
        self.events = self.events[:30]

    def set_connectivity(self, mode: LinkMode):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if mode == LinkMode.FULL:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Fiber / LTE", fallback_link="Satellite", bandwidth_kbps=50000, queued_events=0, last_transition_at=now)
        elif mode == LinkMode.DEGRADED:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Satellite broadband", fallback_link="Narrowband", bandwidth_kbps=2500, queued_events=self.connectivity.queued_events, last_transition_at=now)
        elif mode == LinkMode.CRITICAL:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Narrowband satellite", fallback_link=None, bandwidth_kbps=10, queued_events=self.connectivity.queued_events, last_transition_at=now)
        else:
            self.connectivity = ConnectivityState(mode=mode, primary_link="Local edge only", fallback_link=None, bandwidth_kbps=0, queued_events=self.connectivity.queued_events, last_transition_at=now)
        self._emit("connectivity", RiskLevel.HIGH if mode != LinkMode.FULL else RiskLevel.LOW, f"Connectivity mode: {mode.value}", "Transport policy changed; operations state remains local-first.")

    def tick(self):
        self.tick_count += 1
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for v in self.vessels:
            if v.status in {VesselStatus.INBOUND, VesselStatus.MANEUVERING, VesselStatus.OUTBOUND}:
                distance = max(v.speed_knots, 0.5) * 0.000018
                rad = math.radians(v.heading_deg)
                v.position.lat += math.cos(rad) * distance
                v.position.lon += math.sin(rad) * distance
        self.weather.observed_at = now
        self.weather.wind_knots = round(18 + 4 * math.sin(self.tick_count / 7), 1)
        self.weather.gust_knots = round(self.weather.wind_knots + 7.5, 1)
        self.weather.wave_height_m = round(1.1 + 0.3 * math.sin(self.tick_count / 5), 1)
        self.weather.tide_m = round(0.8 + 0.5 * math.sin(self.tick_count / 14), 2)
        self.weather.restriction_active = self.weather.gust_knots >= 33
        self.weather.restriction_reason = "High-wind pilot/tug restriction" if self.weather.restriction_active else None
        aurora = next(p for p in self.port_calls if p.id == "pc-aurora")
        aurora.delay_minutes = max(0, 8 + int(10 * math.sin(self.tick_count / 8)))
        aurora.estimated_cost_exposure_usd = aurora.delay_minutes * 720
        aurora.risk = RiskLevel.HIGH if aurora.delay_minutes >= 15 else (RiskLevel.MEDIUM if aurora.delay_minutes >= 8 else RiskLevel.LOW)
        if self.connectivity.mode == LinkMode.OFFLINE_EDGE:
            self.connectivity.queued_events += 1
        if self.tick_count % 12 == 0:
            self._emit("port_call", aurora.risk, "MSC Aurora berth window recalculated", f"Current modeled delay is {aurora.delay_minutes} min; exposure ${aurora.estimated_cost_exposure_usd:,.0f}.", vessel_id="v-aurora", berth_id="b-12", port_call_id="pc-aurora")

    def overview(self):
        occupied = sum(1 for b in self.berths if b.status == BerthStatus.OCCUPIED)
        at_risk = sum(1 for p in self.port_calls if p.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL})
        avg_delay = round(sum(p.delay_minutes for p in self.port_calls) / max(len(self.port_calls), 1), 1)
        return HarborOverview(
            generated_at=datetime.now(timezone.utc).replace(microsecond=0), port_name=self.port_name, center=self.center,
            vessels=deepcopy(self.vessels), berths=deepcopy(self.berths), port_calls=deepcopy(self.port_calls),
            weather=deepcopy(self.weather), connectivity=deepcopy(self.connectivity), events=deepcopy(self.events),
            metrics={"vessels_in_port_picture": len(self.vessels), "berths_occupied": occupied, "berths_total": len(self.berths), "port_calls_at_risk": at_risk, "average_delay_minutes": avg_delay},
            data_disclaimer="Demonstration only. Vessel, port-call, risk, and operational data are synthetic."
        )
