from __future__ import annotations

from .models import (
    IncidentType,
    LinkMode,
    ScenarioAction,
    ScenarioActionType,
    ScenarioFixture,
)


SCENARIOS: tuple[ScenarioFixture, ...] = (
    ScenarioFixture(
        id="berth-crunch",
        title="B07 Berth Crunch",
        description="Ever Glory overruns B07 by 90 minutes and creates a downstream Ocean Nova berth conflict.",
        actions=[
            ScenarioAction(
                action_type=ScenarioActionType.INCIDENT,
                incident_type=IncidentType.BERTH_OVERRUN,
                target_port_call_id="pc-glory",
                impact_minutes=90,
            )
        ],
    ),
    ScenarioFixture(
        id="tug-loss",
        title="Tug 14 Unavailable",
        description="Tug 14 fails while serving the modeled Aurora / Glory workload and forces resource recovery planning.",
        actions=[
            ScenarioAction(
                action_type=ScenarioActionType.INCIDENT,
                incident_type=IncidentType.TUG_UNAVAILABLE,
                target_port_call_id="pc-aurora",
                impact_minutes=40,
            )
        ],
    ),
    ScenarioFixture(
        id="edge-pilot-delay",
        title="Offline Edge + Pilot Delay",
        description="The control link drops to offline-edge mode before a 25-minute Aurora pilot delay is recorded locally.",
        actions=[
            ScenarioAction(
                action_type=ScenarioActionType.CONNECTIVITY,
                link_mode=LinkMode.OFFLINE_EDGE,
            ),
            ScenarioAction(
                action_type=ScenarioActionType.INCIDENT,
                incident_type=IncidentType.PILOT_DELAY,
                target_port_call_id="pc-aurora",
                impact_minutes=25,
            ),
        ],
    ),
    ScenarioFixture(
        id="wind-hold",
        title="High-Wind Movement Hold",
        description="A deterministic high-wind restriction holds modeled inbound pilot and tug movements.",
        actions=[
            ScenarioAction(
                action_type=ScenarioActionType.INCIDENT,
                incident_type=IncidentType.WIND_RESTRICTION,
                impact_minutes=30,
            )
        ],
    ),
)


def list_scenarios() -> list[ScenarioFixture]:
    return [item.model_copy(deep=True) for item in SCENARIOS]


def get_scenario(scenario_id: str) -> ScenarioFixture | None:
    return next(
        (item.model_copy(deep=True) for item in SCENARIOS if item.id == scenario_id),
        None,
    )
