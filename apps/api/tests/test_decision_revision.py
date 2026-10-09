"""Workspace invalidation follows engine inputs, not volatile snapshot ticks."""
import pytest

from shorefront_api.simulator import HarborSimulator


@pytest.mark.parametrize('field', ['capacity', 'weather', 'provenance', 'calibration'])
def test_workspace_revision_changes_without_call_or_incident_changes(field):
    simulator = HarborSimulator()
    before = simulator.overview()
    if field == 'capacity':
        simulator.service_resources[0].capacity += 1
    elif field == 'weather':
        simulator.weather.restriction_active = not simulator.weather.restriction_active
    elif field == 'provenance':
        simulator.data_sources[0].provider = 'Updated source attribution'
    else:
        simulator.service_duration_calibrations[0].duration_minutes += 1
    after = simulator.overview()
    assert before.port_calls == after.port_calls
    assert before.incidents == after.incidents
    assert before.decision_revision != after.decision_revision


def test_clock_only_snapshots_have_the_same_nonempty_workspace_revision():
    simulator = HarborSimulator()
    before = simulator.overview()
    simulator.data_sources[0].freshness_seconds += 1
    after = simulator.overview()
    assert before.decision_revision
    assert before.decision_revision == after.decision_revision
