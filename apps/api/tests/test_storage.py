from datetime import timedelta
from pathlib import Path

from portflow_api.adapters import HttpJsonAdapter, configured_live_adapters, get_adapter_snapshot
from portflow_api.domain import detect_berth_conflicts
from portflow_api.models import DataDomain, IncidentType, LinkMode, OperatorRole, ResourceUnavailableWindow, ServiceKind
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


def test_offline_spool_replays_once_with_receipt(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )

    sim.set_connectivity(LinkMode.OFFLINE_EDGE)
    sim.inject_incident(IncidentType.PILOT_DELAY, "pc-aurora", 25)

    pending_before = store.pending_outbound_count()
    assert pending_before >= 2

    sim.set_connectivity(LinkMode.FULL)

    assert store.pending_outbound_count() == 0
    receipts = store.list_replay_receipts(limit=100)
    assert len(receipts) == pending_before

    second = store.replay_outbound_events(lambda event: True)
    assert second == []
    assert len(store.list_replay_receipts(limit=100)) == pending_before


def test_service_graph_propagates_tug_failure(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )

    sim.inject_incident(IncidentType.TUG_UNAVAILABLE, "pc-aurora", 40)
    graph = sim.dependency_graph("pc-aurora")
    nodes = {node["kind"]: node for node in graph["nodes"]}

    assert nodes["tug"]["state"] == "blocked"
    assert nodes["berth"]["state"] == "blocked"
    assert nodes["crane"]["state"] == "blocked"
    assert nodes["departure"]["state"] == "blocked"
    assert nodes["tug"]["resource"]["status"] == "unavailable"


def test_berth_conflict_blocks_later_calls_service_chain(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )

    sim.inject_incident(IncidentType.BERTH_OVERRUN, "pc-glory", 90)
    graph = sim.dependency_graph("pc-nova")
    nodes = {node["kind"]: node for node in graph["nodes"]}

    assert nodes["berth"]["state"] == "blocked"
    assert nodes["crane"]["state"] == "blocked"
    assert nodes["cargo"]["state"] == "blocked"
    assert nodes["departure"]["state"] == "blocked"


def test_tug_recovery_proposal_requires_approval_and_unblocks_target(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )

    sim.inject_incident(IncidentType.TUG_UNAVAILABLE, "pc-aurora", 40)
    proposals = sim.generate_recovery_proposals(call_id="pc-aurora")
    assert proposals
    best = proposals[0]
    assert best.requires_approval is True
    assert any(action.action_type.value == "reassign_resource" for action in best.actions)

    receipt = sim.apply_recovery_proposal(best.id, approved_by="test-operator", approved_role=OperatorRole.OPERATOR, approved_display_name="Test Operator")
    assert receipt.proposal_id == best.id

    graph = sim.dependency_graph("pc-aurora")
    nodes = {node["kind"]: node for node in graph["nodes"]}
    assert nodes["tug"]["state"] != "blocked"
    assert nodes["tug"]["resource"]["id"] != "tug-14"


def test_berth_recovery_prefers_free_compatible_berth(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )

    sim.inject_incident(IncidentType.BERTH_OVERRUN, "pc-glory", 90)
    proposals = sim.generate_recovery_proposals(call_id="pc-nova")
    assert proposals

    best = proposals[0]
    assert best.projected_berth_conflicts == 0
    assert any(
        action.action_type.value == "move_berth" and action.to_berth_id == "b-15"
        for action in best.actions
    )

    receipt = sim.apply_recovery_proposal(best.id, approved_by="test-operator", approved_role=OperatorRole.OPERATOR, approved_display_name="Test Operator")
    assert receipt.resulting_berth_conflicts == 0

    nova = next(call for call in sim.port_calls if call.id == "pc-nova")
    assert nova.berth_id == "b-15"

    graph = sim.dependency_graph("pc-nova")
    nodes = {node["kind"]: node for node in graph["nodes"]}
    assert nodes["berth"]["resource"]["id"] == "b-15"
    assert nodes["crane"]["resource"]["id"] == "crane-b15-a"


def test_recovery_proposals_are_deterministic_and_stale_after_apply(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )

    sim.inject_incident(IncidentType.BERTH_OVERRUN, "pc-glory", 90)
    first = sim.generate_recovery_proposals(call_id="pc-nova")
    second = sim.generate_recovery_proposals(call_id="pc-nova")
    assert [item.id for item in first] == [item.id for item in second]

    proposal_id = first[0].id
    sim.apply_recovery_proposal(proposal_id, approved_by="test-operator", approved_role=OperatorRole.OPERATOR, approved_display_name="Test Operator")

    try:
        sim.apply_recovery_proposal(proposal_id, approved_by="test-operator", approved_role=OperatorRole.OPERATOR, approved_display_name="Test Operator")
    except ValueError as exc:
        assert "stale" in str(exc).lower() or "already applied" in str(exc).lower()
    else:
        raise AssertionError("Applied recovery proposal must become stale")


def test_recovery_application_receipt_is_persisted(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    sim.inject_incident(IncidentType.BERTH_OVERRUN, "pc-glory", 90)
    proposal = sim.generate_recovery_proposals(call_id="pc-nova")[0]
    receipt = sim.apply_recovery_proposal(proposal.id, approved_by="test-operator", approved_role=OperatorRole.OPERATOR, approved_display_name="Test Operator")

    stored = store.list_recovery_receipts(limit=10)
    assert len(stored) == 1
    assert stored[0].proposal_id == receipt.proposal_id
    assert stored[0].approved_by == "test-operator"
    assert stored[0].approved_role == OperatorRole.OPERATOR
    assert stored[0].approved_display_name == "Test Operator"
    assert stored[0].resulting_berth_conflicts == 0


def test_compound_tug_recovery_clears_global_service_blocks(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    sim.inject_incident(IncidentType.TUG_UNAVAILABLE, "pc-aurora", 40)
    proposal = sim.generate_recovery_proposals(call_id="pc-aurora")[0]
    receipt = sim.apply_recovery_proposal(proposal.id, approved_by="test-operator", approved_role=OperatorRole.OPERATOR, approved_display_name="Test Operator")

    assert receipt.resulting_blocked_services == 0
    assert len([a for a in proposal.actions if a.action_type.value == "reassign_resource"]) >= 2


def test_recovery_proposal_id_changes_when_relevant_state_changes(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    sim.inject_incident(IncidentType.BERTH_OVERRUN, "pc-glory", 90)
    first = sim.generate_recovery_proposals(call_id="pc-nova")
    assert first
    old_id = first[0].id
    old_fingerprint = first[0].state_fingerprint

    sim.inject_incident(IncidentType.PILOT_DELAY, "pc-aurora", 25)
    second = sim.generate_recovery_proposals(call_id="pc-nova")
    assert second
    assert second[0].state_fingerprint != old_fingerprint
    assert all(item.id != old_id for item in second)

    try:
        sim.apply_recovery_proposal(old_id, approved_by="test-operator", approved_role=OperatorRole.OPERATOR, approved_display_name="Test Operator")
    except ValueError as exc:
        assert "stale" in str(exc).lower() or "unavailable" in str(exc).lower()
    else:
        raise AssertionError("Old state-bound proposal must be rejected")


def test_recovery_ranks_later_free_tug_above_busier_tug(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    sim.inject_incident(IncidentType.TUG_UNAVAILABLE, "pc-aurora", 40)
    proposals = sim.generate_recovery_proposals(call_id="pc-aurora")

    assert len(proposals) >= 2
    assert "Tug 31" in proposals[0].title
    assert "Tug 22" in proposals[1].title
    assert proposals[0].projected_total_delay_minutes < proposals[1].projected_total_delay_minutes
    assert proposals[0].disruption_score < proposals[1].disruption_score

    tug31 = next(resource for resource in sim.service_resources if resource.id == "tug-31")
    assert tug31.available_from is not None

    shifts = [
        action.shift_minutes
        for action in proposals[0].actions
        if action.action_type.value == "shift_window"
    ]
    assert shifts == [20]


def test_domain_rejects_viewer_recovery_approval(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    sim.inject_incident(IncidentType.BERTH_OVERRUN, "pc-glory", 90)
    proposal = sim.generate_recovery_proposals(call_id="pc-nova")[0]
    conflicts_before = detect_berth_conflicts(sim.port_calls)

    try:
        sim.apply_recovery_proposal(
            proposal.id,
            approved_by="viewer-direct",
            approved_role=OperatorRole.VIEWER,
            approved_display_name="Read Only",
        )
    except ValueError as exc:
        assert "operator or supervisor" in str(exc).lower()
    else:
        raise AssertionError("Viewer must not be able to approve recovery in domain layer")

    assert detect_berth_conflicts(sim.port_calls) == conflicts_before
    assert store.list_recovery_receipts(limit=10) == []


def test_recorded_ais_ingest_updates_source_and_survives_restart(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
    )

    snapshot = get_adapter_snapshot("recorded-ais")
    assert snapshot is not None
    applied = sim.ingest_adapter_snapshot(snapshot)
    assert applied == 2

    aurora = next(v for v in sim.vessels if v.id == "v-aurora")
    assert aurora.source_id == "recorded-ais"
    assert aurora.position.lat == 51.982
    assert aurora.position.lon == 3.995

    source = next(item for item in sim.data_sources if item.source_id == "recorded-ais")
    assert source.mode.value == "recorded"
    assert source.provider == "PortFlow recorded AIS fixture"
    assert source.stale is False

    restored = HarborSimulator(initial=store.load_snapshot())
    restored_aurora = next(v for v in restored.vessels if v.id == "v-aurora")
    assert restored_aurora.source_id == "recorded-ais"
    restored_source = next(item for item in restored.data_sources if item.domain.value == "ais")
    assert restored_source.source_id == "recorded-ais"


def test_recorded_weather_ingest_replaces_weather_provenance(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(snapshot_sink=store.save_snapshot)

    snapshot = get_adapter_snapshot("recorded-weather")
    assert snapshot is not None
    assert sim.ingest_adapter_snapshot(snapshot) == 1

    assert sim.weather.source_id == "recorded-weather"
    assert sim.weather.wind_knots == 23.0
    assert sim.weather.gust_knots == 31.0
    source = next(item for item in sim.data_sources if item.domain.value == "weather_tide")
    assert source.freshness_seconds == 42
    assert source.health.value == "healthy"


def test_recorded_berth_plan_ingest_is_idempotent_against_absolute_offsets(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(snapshot_sink=store.save_snapshot)

    snapshot = get_adapter_snapshot("recorded-berth-plan")
    assert snapshot is not None
    first = sim.ingest_adapter_snapshot(snapshot)
    nova_first = next(call for call in sim.port_calls if call.id == "pc-nova")
    first_arrival = nova_first.arrival_eta

    second = sim.ingest_adapter_snapshot(snapshot)
    nova_second = next(call for call in sim.port_calls if call.id == "pc-nova")

    assert first == 2
    assert second == 2
    assert nova_second.arrival_eta == first_arrival
    assert nova_second.source_id == "recorded-berth-plan"


def test_stale_adapter_preview_is_rejected_for_ingest(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(snapshot_sink=store.save_snapshot)

    snapshot = get_adapter_snapshot("stale-weather-fixture")
    assert snapshot is not None
    assert snapshot.provenance.stale is True
    assert snapshot.provenance.health.value == "stale"

    before = sim.weather.model_copy(deep=True)
    try:
        sim.ingest_adapter_snapshot(snapshot)
    except ValueError as exc:
        assert "not ingestible" in str(exc).lower()
        assert "stale" in str(exc).lower()
    else:
        raise AssertionError("Stale adapter snapshot must not be ingested")

    assert sim.weather == before


def test_recorded_source_freshness_ages_into_stale_health(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(snapshot_sink=store.save_snapshot)

    snapshot = get_adapter_snapshot("recorded-weather")
    assert snapshot is not None
    sim.ingest_adapter_snapshot(snapshot)

    source = next(item for item in sim.data_sources if item.domain.value == "weather_tide")
    source.observed_at = source.observed_at - __import__("datetime").timedelta(seconds=600)

    overview = sim.overview()
    aged = next(item for item in overview.data_sources if item.domain.value == "weather_tide")

    assert aged.freshness_seconds > aged.stale_after_seconds
    assert aged.stale is True
    assert aged.health.value == "stale"
    assert overview.metrics["stale_data_sources"] == 1


def test_invalid_adapter_payload_is_rejected_before_any_partial_mutation(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(snapshot_sink=store.save_snapshot)

    snapshot = get_adapter_snapshot("recorded-ais")
    assert snapshot is not None
    snapshot.records.append({
        "vessel_id": "v-lima",
        "lat": 999,
        "lon": 4.0,
        "speed_knots": 1.0,
        "heading_deg": 90.0,
    })

    before = {
        vessel.id: vessel.model_copy(deep=True)
        for vessel in sim.vessels
    }

    try:
        sim.ingest_adapter_snapshot(snapshot)
    except ValueError as exc:
        assert "invalid ais adapter payload" in str(exc).lower()
    else:
        raise AssertionError("Malformed adapter payload must be rejected")

    for vessel in sim.vessels:
        assert vessel == before[vessel.id]

    ais_source = next(source for source in sim.data_sources if source.domain.value == "ais")
    assert ais_source.source_id == "synthetic-ais"


def test_live_adapter_ingest_changes_disclaimer_truthfully(tmp_path):
    from datetime import datetime, timezone

    store = make_store(tmp_path)
    sim = HarborSimulator(snapshot_sink=store.save_snapshot)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    adapter = HttpJsonAdapter(
        adapter_id="live-weather-test",
        domain=DataDomain.WEATHER_TIDE,
        provider="Test Live Weather",
        url="https://example.invalid/weather",
        stale_after_seconds=300,
        loader=lambda url, timeout: {
            "observed_at": now.isoformat(),
            "records": [{
                "wind_knots": 20.0,
                "gust_knots": 25.0,
                "visibility_km": 9.0,
                "wave_height_m": 1.1,
                "tide_m": 0.7,
            }],
        },
    )

    snapshot = adapter.snapshot(now=now)
    assert snapshot.provenance.mode.value == "live"
    assert snapshot.provenance.health.value == "healthy"

    sim.ingest_adapter_snapshot(snapshot)
    overview = sim.overview()

    assert overview.weather.source_id == "live-weather-test"
    assert "live adapter data" in overview.data_disclaimer.lower()
    assert "all data are synthetic" not in overview.data_disclaimer.lower()


def test_background_tick_does_not_synthetically_move_recorded_ais():
    sim = HarborSimulator()
    snapshot = get_adapter_snapshot("recorded-ais")
    assert snapshot is not None
    sim.ingest_adapter_snapshot(snapshot)

    aurora = next(v for v in sim.vessels if v.id == "v-aurora")
    seaway = next(v for v in sim.vessels if v.id == "v-seaway")
    aurora_before = aurora.position.model_copy(deep=True)
    seaway_before = seaway.position.model_copy(deep=True)

    sim.tick()

    assert aurora.position == aurora_before
    assert seaway.position != seaway_before


def test_background_tick_does_not_synthetically_overwrite_recorded_weather():
    sim = HarborSimulator()
    snapshot = get_adapter_snapshot("recorded-weather")
    assert snapshot is not None
    sim.ingest_adapter_snapshot(snapshot)

    before = sim.weather.model_copy(deep=True)
    sim.tick()

    assert sim.weather == before
    assert sim.weather.source_id == "recorded-weather"


def test_bunker_failure_blocks_shared_resource_workload_and_departure(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    incident = sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        45,
    )
    assert incident.target_resource_id == "bunker-barge-4"

    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-4"
    )
    assert resource.status.value == "unavailable"

    for call_id in ("pc-aurora", "pc-glory"):
        graph = sim.dependency_graph(call_id)
        nodes = {node["kind"]: node for node in graph["nodes"]}
        assert nodes["bunker"]["state"] == "blocked"
        assert nodes["departure"]["state"] == "blocked"


def test_bunker_recovery_ranks_delayed_spare_above_busy_barge_and_unblocks(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        45,
    )
    proposals = [
        proposal
        for proposal in sim.generate_recovery_proposals(call_id="pc-aurora")
        if any(
            action.service_kind == ServiceKind.BUNKER
            for action in proposal.actions
        )
    ]

    assert len(proposals) >= 2
    assert "Bunker Barge 12" in proposals[0].title
    assert "Bunker Barge 9" in proposals[1].title
    assert proposals[0].disruption_score < proposals[1].disruption_score
    assert proposals[0].projected_total_delay_minutes < proposals[1].projected_total_delay_minutes
    assert proposals[0].projected_blocked_services == 0

    reassignments = [
        action
        for action in proposals[0].actions
        if action.action_type.value == "reassign_resource"
        and action.service_kind == ServiceKind.BUNKER
    ]
    assert {action.port_call_id for action in reassignments} == {
        "pc-aurora",
        "pc-glory",
    }

    receipt = sim.apply_recovery_proposal(
        proposals[0].id,
        approved_by="ops-bunker",
        approved_role=OperatorRole.OPERATOR,
        approved_display_name="Bunker Ops",
    )
    assert receipt.resulting_blocked_services == 0

    for call_id in ("pc-aurora", "pc-glory"):
        graph = sim.dependency_graph(call_id)
        nodes = {node["kind"]: node for node in graph["nodes"]}
        assert nodes["bunker"]["state"] != "blocked"
        assert nodes["departure"]["state"] != "blocked"


def test_v08_snapshot_service_graph_migrates_to_v09_dag(tmp_path):
    store = make_store(tmp_path)
    original = HarborSimulator(snapshot_sink=store.save_snapshot)
    snapshot = original.overview()

    old_kinds = {
        ServiceKind.PILOT,
        ServiceKind.TUG,
        ServiceKind.BERTH,
        ServiceKind.CRANE,
        ServiceKind.CARGO,
        ServiceKind.CUSTOMS,
        ServiceKind.DEPARTURE,
    }
    snapshot.service_steps = [
        step for step in snapshot.service_steps
        if step.kind in old_kinds
    ]

    restored = HarborSimulator(initial=snapshot)
    kinds = {
        step.kind
        for step in restored.service_steps
        if step.port_call_id == "pc-aurora"
    }
    assert {
        ServiceKind.BUNKER,
        ServiceKind.STORES,
        ServiceKind.DOCUMENTS,
        ServiceKind.GATE,
    } <= kinds
    assert len(kinds) == 11


def test_partially_upgraded_snapshot_rebuilds_every_service_graph(tmp_path):
    store = make_store(tmp_path)
    original = HarborSimulator(snapshot_sink=store.save_snapshot)
    snapshot = original.overview()

    v09_only = {
        ServiceKind.BUNKER,
        ServiceKind.STORES,
        ServiceKind.DOCUMENTS,
        ServiceKind.GATE,
    }
    snapshot.service_steps = [
        step
        for step in snapshot.service_steps
        if step.port_call_id == "pc-aurora" or step.kind not in v09_only
    ]

    restored = HarborSimulator(initial=snapshot)

    for call in restored.port_calls:
        kinds = {
            step.kind
            for step in restored.service_steps
            if step.port_call_id == call.id
        }
        assert {
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
        } == kinds


def test_resource_shift_respects_explicit_unavailable_calendar_window():
    sim = HarborSimulator()
    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-12"
    )
    target = next(
        step for step in sim.service_steps
        if step.port_call_id == "pc-glory" and step.kind == ServiceKind.BUNKER
    )

    resource.unavailable_windows = [
        ResourceUnavailableWindow(
            start_at=sim._started + timedelta(minutes=95),
            end_at=sim._started + timedelta(minutes=140),
            reason="planned maintenance",
        )
    ]

    shift = sim._resource_shift_needed(
        target.port_call_id,
        ServiceKind.BUNKER,
        resource.id,
        separation_minutes=60,
    )

    assert target.planned_at == sim._started + timedelta(minutes=97)
    assert shift == 43


def test_resource_calendar_change_invalidates_recovery_fingerprint():
    sim = HarborSimulator()
    sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        45,
    )
    before = sim.generate_recovery_proposals(call_id="pc-aurora")[0].state_fingerprint

    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-12"
    )
    resource.unavailable_windows = [
        ResourceUnavailableWindow(
            start_at=sim._started + timedelta(minutes=95),
            end_at=sim._started + timedelta(minutes=140),
            reason="planned maintenance",
        )
    ]

    after = sim.generate_recovery_proposals(call_id="pc-aurora")[0].state_fingerprint
    assert after != before


def test_resource_calendar_can_change_recovery_ranking():
    sim = HarborSimulator()
    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-12"
    )
    resource.unavailable_windows = [
        ResourceUnavailableWindow(
            start_at=sim._started + timedelta(minutes=95),
            end_at=sim._started + timedelta(minutes=300),
            reason="extended maintenance",
        )
    ]

    sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        45,
    )
    proposals = [
        proposal
        for proposal in sim.generate_recovery_proposals(call_id="pc-aurora")
        if any(
            action.service_kind == ServiceKind.BUNKER
            for action in proposal.actions
        )
    ]

    assert "Bunker Barge 9" in proposals[0].title
    assert "Bunker Barge 12" in proposals[1].title
    assert proposals[0].disruption_score < proposals[1].disruption_score


def test_live_adapter_falls_back_to_fresh_last_good_as_degraded_preview():
    from datetime import datetime, timezone

    base = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    calls = {"count": 0}

    def loader(url, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "observed_at": base.isoformat(),
                "records": [{"vessel_id": "v-aurora", "lat": 51.9, "lon": 4.0}],
            }
        raise TimeoutError("fixture timeout")

    adapter = HttpJsonAdapter(
        adapter_id="live-ais-cache-test",
        domain=DataDomain.AIS,
        provider="Cache Test",
        url="https://example.invalid/ais",
        stale_after_seconds=120,
        loader=loader,
    )

    healthy = adapter.snapshot(now=base)
    degraded = adapter.snapshot(now=base + timedelta(seconds=30))

    assert healthy.provenance.health.value == "healthy"
    assert healthy.provenance.last_success_at == base
    assert degraded.provenance.health.value == "degraded"
    assert degraded.provenance.stale is False
    assert degraded.provenance.using_cached_records is True
    assert degraded.provenance.consecutive_errors == 1
    assert degraded.provenance.last_success_at == base
    assert degraded.records == healthy.records


def test_live_adapter_cached_preview_becomes_stale_after_threshold():
    from datetime import datetime, timezone

    base = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    calls = {"count": 0}

    def loader(url, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "observed_at": base.isoformat(),
                "records": [{"wind_knots": 12.0}],
            }
        raise ConnectionError("fixture offline")

    adapter = HttpJsonAdapter(
        adapter_id="live-weather-cache-test",
        domain=DataDomain.WEATHER_TIDE,
        provider="Cache Test",
        url="https://example.invalid/weather",
        stale_after_seconds=60,
        loader=loader,
    )

    adapter.snapshot(now=base)
    stale = adapter.snapshot(now=base + timedelta(seconds=90))

    assert stale.provenance.health.value == "stale"
    assert stale.provenance.stale is True
    assert stale.provenance.using_cached_records is True
    assert stale.provenance.consecutive_errors == 1


def test_live_adapter_without_last_good_reports_error_streak():
    from datetime import datetime, timezone

    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    adapter = HttpJsonAdapter(
        adapter_id="live-error-test",
        domain=DataDomain.AIS,
        provider="Error Test",
        url="https://example.invalid/ais",
        stale_after_seconds=120,
        loader=lambda url, timeout: (_ for _ in ()).throw(TimeoutError("down")),
    )

    first = adapter.snapshot(now=now)
    second = adapter.snapshot(now=now + timedelta(seconds=5))

    assert first.provenance.health.value == "error"
    assert first.provenance.consecutive_errors == 1
    assert first.provenance.last_success_at is None
    assert first.records == []
    assert second.provenance.consecutive_errors == 2


def test_degraded_cached_snapshot_cannot_mutate_harbor_truth():
    from datetime import datetime, timezone

    base = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    calls = {"count": 0}

    def loader(url, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "observed_at": base.isoformat(),
                "records": [{
                    "vessel_id": "v-aurora",
                    "lat": 51.9,
                    "lon": 4.0,
                    "speed_knots": 8.0,
                    "heading_deg": 90.0,
                }],
            }
        raise TimeoutError("down")

    adapter = HttpJsonAdapter(
        adapter_id="live-ais-ingest-gate-test",
        domain=DataDomain.AIS,
        provider="Gate Test",
        url="https://example.invalid/ais",
        stale_after_seconds=120,
        loader=loader,
    )
    adapter.snapshot(now=base)
    degraded = adapter.snapshot(now=base + timedelta(seconds=30))
    sim = HarborSimulator()

    try:
        sim.ingest_adapter_snapshot(degraded)
    except ValueError as exc:
        assert "degraded" in str(exc).lower()
    else:
        raise AssertionError("Degraded cached preview must not be ingestible")


def test_configured_live_adapter_instance_is_reused_while_config_is_unchanged(monkeypatch):
    monkeypatch.setenv("PORTFLOW_AIS_URL", "https://example.invalid/ais")
    monkeypatch.setenv("PORTFLOW_AIS_PROVIDER", "Persistent AIS")

    first = configured_live_adapters()["live-ais"]
    second = configured_live_adapters()["live-ais"]
    assert first is second

    monkeypatch.setenv("PORTFLOW_AIS_PROVIDER", "Changed AIS")
    third = configured_live_adapters()["live-ais"]
    assert third is not first
