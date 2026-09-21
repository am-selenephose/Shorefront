from pathlib import Path

from portflow_api.domain import detect_berth_conflicts
from portflow_api.models import IncidentType
from portflow_api.simulator import HarborSimulator
from portflow_api.storage import OperationsStore


def make_store(tmp_path: Path) -> OperationsStore:
    store = OperationsStore(f"sqlite:///{tmp_path / 'portflow-test.db'}")
    store.init_schema()
    return store


def test_snapshot_survives_simulator_restart(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
    )

    incident = sim.inject_incident(IncidentType.BERTH_OVERRUN, "pc-glory", 90)
    assert incident.target_berth_id == "b-07"
    conflicts_before = detect_berth_conflicts(sim.port_calls)
    assert conflicts_before
    assert any(c.berth_id == "b-07" for c in conflicts_before)

    snapshot = store.load_snapshot()
    assert snapshot is not None

    restarted = HarborSimulator(
        initial=snapshot,
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
    )
    assert restarted.incidents[0].id == incident.id
    conflicts_after = detect_berth_conflicts(restarted.port_calls)
    assert conflicts_after == conflicts_before


def test_event_ledger_is_append_only_and_idempotent(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
    )
    sim.inject_incident(IncidentType.PILOT_DELAY, "pc-aurora", 25)
    ledger = store.list_events(limit=50)
    assert len(ledger) >= 2
    event = ledger[0]
    assert store.append_event(event) is False
    assert len(store.list_events(limit=50)) == len(ledger)


def test_incident_store_tracks_resolution(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
    )
    incident = sim.inject_incident(IncidentType.TUG_UNAVAILABLE, "pc-aurora", 40)
    sim.resolve_incident(incident.id)
    stored = store.list_incidents()
    assert stored[0].status.value == "resolved"
    assert stored[0].resolved_at is not None
