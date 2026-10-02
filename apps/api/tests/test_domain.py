from datetime import datetime, timedelta, timezone

from shorefront_api.domain import dependency_violations, detect_berth_conflicts, score_port_call
from shorefront_api.models import PortCall, PortCallStage, RiskLevel, WeatherState


def make_call(call_id: str, berth: str, start: datetime, duration_h: int = 4, delay: int = 0):
    return PortCall(
        id=call_id,
        vessel_id=f"v-{call_id}",
        berth_id=berth,
        arrival_eta=start,
        departure_eta=start + timedelta(hours=duration_h),
        delay_minutes=delay,
        stages=[
            PortCallStage(code="pilot", label="Pilot", planned_at=start - timedelta(minutes=30)),
            PortCallStage(code="berth", label="Berth", planned_at=start, dependency_codes=["pilot"]),
        ],
    )


def weather(restricted: bool = False):
    return WeatherState(
        observed_at=datetime.now(timezone.utc),
        wind_knots=20,
        gust_knots=34 if restricted else 25,
        visibility_km=9,
        wave_height_m=1.2,
        tide_m=0.8,
        restriction_active=restricted,
        restriction_reason="High-wind pilot restriction" if restricted else None,
    )


def test_conflict_detector_finds_overlap_on_same_berth():
    t = datetime(2026, 9, 21, 8, tzinfo=timezone.utc)
    calls = [
        make_call("a", "b-1", t, 4),
        make_call("b", "b-1", t + timedelta(hours=3), 4),
        make_call("c", "b-2", t + timedelta(hours=3), 4),
    ]
    conflicts = detect_berth_conflicts(calls)
    assert len(conflicts) == 1
    assert conflicts[0].berth_id == "b-1"
    assert conflicts[0].overlap_minutes == 60


def test_risk_engine_combines_delay_weather_and_conflict():
    t = datetime(2026, 9, 21, 8, tzinfo=timezone.utc)
    call = make_call("a", "b-1", t, delay=18)
    level, score, reasons = score_port_call(call, weather(restricted=True), berth_conflicted=True)
    assert level == RiskLevel.CRITICAL
    assert score >= 7
    assert "berth schedule conflict" in reasons


def test_dependency_ordering_is_mechanical():
    t = datetime(2026, 9, 21, 8, tzinfo=timezone.utc)
    call = make_call("a", "b-1", t)
    call.stages[0].planned_at = t + timedelta(minutes=20)
    assert dependency_violations(call) == [("berth", "pilot")]
