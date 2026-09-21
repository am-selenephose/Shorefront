from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .models import PortCall, RiskLevel, WeatherState


@dataclass(frozen=True)
class BerthConflict:
    berth_id: str
    first_call_id: str
    second_call_id: str
    overlap_minutes: int


def detect_berth_conflicts(calls: list[PortCall]) -> list[BerthConflict]:
    conflicts: list[BerthConflict] = []
    by_berth: dict[str, list[PortCall]] = {}
    for call in calls:
        by_berth.setdefault(call.berth_id, []).append(call)

    for berth_id, items in by_berth.items():
        ordered = sorted(items, key=lambda c: c.arrival_eta)
        for idx, left in enumerate(ordered):
            for right in ordered[idx + 1:]:
                overlap_start = max(left.arrival_eta, right.arrival_eta)
                overlap_end = min(left.departure_eta, right.departure_eta)
                if overlap_end > overlap_start:
                    conflicts.append(BerthConflict(
                        berth_id=berth_id,
                        first_call_id=left.id,
                        second_call_id=right.id,
                        overlap_minutes=int((overlap_end - overlap_start).total_seconds() // 60),
                    ))
    return conflicts


def dependency_violations(call: PortCall) -> list[tuple[str, str]]:
    by_code = {stage.code: stage for stage in call.stages}
    violations: list[tuple[str, str]] = []
    for stage in call.stages:
        for dep_code in stage.dependency_codes:
            dep = by_code.get(dep_code)
            if dep is None or dep.planned_at > stage.planned_at:
                violations.append((stage.code, dep_code))
    return violations


def shift_call_from_stage(call: PortCall, from_stage_code: str, delay_minutes: int) -> None:
    if delay_minutes <= 0:
        return
    codes = [stage.code for stage in call.stages]
    if from_stage_code not in codes:
        raise ValueError(f"Unknown stage {from_stage_code}")
    start_idx = codes.index(from_stage_code)
    delta = timedelta(minutes=delay_minutes)
    for stage in call.stages[start_idx:]:
        stage.planned_at += delta
    if from_stage_code in {"pilot", "pilot_board", "tug", "berth"}:
        call.arrival_eta += delta
    call.departure_eta += delta
    call.delay_minutes += delay_minutes


def extend_departure(call: PortCall, delay_minutes: int) -> None:
    if delay_minutes <= 0:
        return
    delta = timedelta(minutes=delay_minutes)
    call.departure_eta += delta
    for stage in call.stages:
        if stage.code == "departure":
            stage.planned_at += delta
    call.delay_minutes += delay_minutes


def score_port_call(
    call: PortCall,
    weather: WeatherState,
    berth_conflicted: bool,
) -> tuple[RiskLevel, int, list[str]]:
    score = 0
    reasons: list[str] = []

    if call.delay_minutes >= 60:
        score += 5
        reasons.append("delay >= 60 min")
    elif call.delay_minutes >= 30:
        score += 4
        reasons.append("delay >= 30 min")
    elif call.delay_minutes >= 15:
        score += 3
        reasons.append("delay >= 15 min")
    elif call.delay_minutes >= 8:
        score += 1
        reasons.append("delay >= 8 min")

    if weather.restriction_active:
        score += 3
        reasons.append(weather.restriction_reason or "weather restriction")

    if weather.gust_knots >= 30:
        score += 1
        reasons.append("gust >= 30 kt")

    if berth_conflicted:
        score += 4
        reasons.append("berth schedule conflict")

    if dependency_violations(call):
        score += 4
        reasons.append("invalid port-call dependency ordering")

    if score >= 7:
        return RiskLevel.CRITICAL, score, reasons
    if score >= 4:
        return RiskLevel.HIGH, score, reasons
    if score >= 2:
        return RiskLevel.MEDIUM, score, reasons
    return RiskLevel.LOW, score, reasons
