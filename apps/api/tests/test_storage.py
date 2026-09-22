from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from portflow_api.adapters import HttpJsonAdapter, configured_live_adapters, get_adapter_snapshot
from portflow_api.domain import detect_berth_conflicts
from portflow_api.models import AdapterHealth, DataDomain, DataSourceMode, DataSourceProvenance, IncidentType, LinkMode, OperatorRole, ResourceUnavailableWindow, ServiceDurationCalibration, ServiceKind
from portflow_api.simulator import HarborSimulator, RecoveryProposalStaleError
from portflow_api.storage import OperationsStore, normalize_database_url


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


def test_recovery_confidence_is_demo_for_synthetic_only_inputs():
    sim = HarborSimulator()
    sim.inject_incident(IncidentType.BUNKER_UNAVAILABLE, "pc-aurora", 45)

    proposal = sim.generate_recovery_proposals(call_id="pc-aurora")[0]
    assert proposal.decision_confidence.value == "demo"
    assert any("synthetic demo" in warning.lower() for warning in proposal.data_quality_warnings)


def test_recorded_ingest_changes_recovery_confidence_and_fingerprint():
    sim = HarborSimulator()
    sim.inject_incident(IncidentType.BUNKER_UNAVAILABLE, "pc-aurora", 45)
    before = sim.generate_recovery_proposals(call_id="pc-aurora")[0]

    snapshot = get_adapter_snapshot("recorded-ais")
    assert snapshot is not None
    sim.ingest_adapter_snapshot(snapshot)
    after = sim.generate_recovery_proposals(call_id="pc-aurora")[0]

    assert before.decision_confidence.value == "demo"
    assert after.decision_confidence.value == "medium"
    assert after.state_fingerprint != before.state_fingerprint
    assert any("recorded replay" in warning.lower() for warning in after.data_quality_warnings)
    assert any("mixes synthetic" in warning.lower() for warning in after.data_quality_warnings)


def test_stale_active_source_drives_low_recovery_confidence():
    sim = HarborSimulator()
    snapshot = get_adapter_snapshot("recorded-ais")
    assert snapshot is not None
    sim.ingest_adapter_snapshot(snapshot)

    source = next(item for item in sim.data_sources if item.source_id == "recorded-ais")
    source.observed_at = source.observed_at - timedelta(hours=1)
    source.stale_after_seconds = 1

    sim.inject_incident(IncidentType.BUNKER_UNAVAILABLE, "pc-aurora", 45)
    proposal = sim.generate_recovery_proposals(call_id="pc-aurora")[0]

    assert proposal.decision_confidence.value == "low"
    assert any("recorded-ais" in warning for warning in proposal.data_quality_warnings)


def test_all_healthy_live_active_sources_can_be_high_confidence():
    from datetime import datetime, timezone

    sim = HarborSimulator()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    for vessel in sim.vessels:
        vessel.source_id = "live-ais-proof"
    for berth in sim.berths:
        berth.source_id = "live-berth-proof"
    for call in sim.port_calls:
        call.source_id = "live-berth-proof"
    sim.weather.source_id = "live-weather-proof"
    for calibration in sim.service_duration_calibrations:
        calibration.source_id = "live-calibration-proof"
        calibration.mode = DataSourceMode.LIVE
        calibration.provider = "Live Calibration Proof"
        calibration.observed_at = now

    sim.data_sources = [
        DataSourceProvenance(
            source_id="live-ais-proof",
            domain=DataDomain.AIS,
            mode=DataSourceMode.LIVE,
            provider="Live AIS Proof",
            observed_at=now,
            received_at=now,
            stale_after_seconds=120,
            health=AdapterHealth.HEALTHY,
            record_count=len(sim.vessels),
        ),
        DataSourceProvenance(
            source_id="live-weather-proof",
            domain=DataDomain.WEATHER_TIDE,
            mode=DataSourceMode.LIVE,
            provider="Live Weather Proof",
            observed_at=now,
            received_at=now,
            stale_after_seconds=300,
            health=AdapterHealth.HEALTHY,
            record_count=1,
        ),
        DataSourceProvenance(
            source_id="live-berth-proof",
            domain=DataDomain.BERTH_PLAN,
            mode=DataSourceMode.LIVE,
            provider="Live Berth Proof",
            observed_at=now,
            received_at=now,
            stale_after_seconds=600,
            health=AdapterHealth.HEALTHY,
            record_count=len(sim.port_calls),
        ),
        DataSourceProvenance(
            source_id="live-calibration-proof",
            domain=DataDomain.SERVICE_CALIBRATION,
            mode=DataSourceMode.LIVE,
            provider="Live Calibration Proof",
            observed_at=now,
            received_at=now,
            stale_after_seconds=86_400,
            health=AdapterHealth.HEALTHY,
            record_count=len(sim.service_duration_calibrations),
        ),
    ]

    sim.inject_incident(IncidentType.BUNKER_UNAVAILABLE, "pc-aurora", 45)
    proposal = sim.generate_recovery_proposals(call_id="pc-aurora")[0]

    assert proposal.decision_confidence.value == "high"
    assert proposal.data_quality_warnings == []


def test_interval_capacity_one_delays_overlapping_bunker_assignment():
    sim = HarborSimulator()
    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-12"
    )
    resource.available_from = None
    resource.unavailable_windows = []
    resource.capacity = 1

    target = next(
        step for step in sim.service_steps
        if step.port_call_id == "pc-glory" and step.kind == ServiceKind.BUNKER
    )
    other = next(
        step for step in sim.service_steps
        if step.port_call_id == "pc-lima" and step.kind == ServiceKind.BUNKER
    )
    other.resource_id = resource.id
    other.planned_at = sim._started + timedelta(minutes=120)
    other.duration_minutes = 60

    assert target.planned_at == sim._started + timedelta(minutes=97)
    shift = sim._resource_shift_needed(
        target.port_call_id,
        ServiceKind.BUNKER,
        resource.id,
        separation_minutes=60,
    )
    assert shift == 83


def test_interval_capacity_two_allows_one_overlapping_assignment():
    sim = HarborSimulator()
    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-12"
    )
    resource.available_from = None
    resource.unavailable_windows = []
    resource.capacity = 2

    other = next(
        step for step in sim.service_steps
        if step.port_call_id == "pc-lima" and step.kind == ServiceKind.BUNKER
    )
    other.resource_id = resource.id
    other.planned_at = sim._started + timedelta(minutes=120)
    other.duration_minutes = 60

    shift = sim._resource_shift_needed(
        "pc-glory",
        ServiceKind.BUNKER,
        resource.id,
        separation_minutes=60,
    )
    assert shift == 0


def test_interval_capacity_two_delays_when_two_assignments_saturate_resource():
    sim = HarborSimulator()
    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-12"
    )
    resource.available_from = None
    resource.unavailable_windows = []
    resource.capacity = 2

    lima = next(
        step for step in sim.service_steps
        if step.port_call_id == "pc-lima" and step.kind == ServiceKind.BUNKER
    )
    nova = next(
        step for step in sim.service_steps
        if step.port_call_id == "pc-nova" and step.kind == ServiceKind.BUNKER
    )
    lima.resource_id = resource.id
    nova.resource_id = resource.id
    lima.planned_at = sim._started + timedelta(minutes=100)
    nova.planned_at = sim._started + timedelta(minutes=120)
    lima.duration_minutes = 60
    nova.duration_minutes = 60

    shift = sim._resource_shift_needed(
        "pc-glory",
        ServiceKind.BUNKER,
        resource.id,
        separation_minutes=60,
    )
    assert shift == 63


def test_calendar_outage_blocks_service_interval_not_only_start_time():
    sim = HarborSimulator()
    resource = next(
        item for item in sim.service_resources
        if item.id == "bunker-barge-12"
    )
    resource.available_from = None
    resource.capacity = 1
    resource.unavailable_windows = [
        ResourceUnavailableWindow(
            start_at=sim._started + timedelta(minutes=120),
            end_at=sim._started + timedelta(minutes=140),
            reason="maintenance during service",
        )
    ]

    # Glory starts at +97 and the modeled bunker duration is 60 minutes, so
    # the job overlaps a +120..+140 outage even though it starts beforehand.
    shift = sim._resource_shift_needed(
        "pc-glory",
        ServiceKind.BUNKER,
        resource.id,
        separation_minutes=60,
    )
    assert shift == 43


def test_legacy_zero_duration_steps_are_migrated_on_restore():
    sim = HarborSimulator()
    snapshot = sim.overview()
    for step in snapshot.service_steps:
        step.duration_minutes = 0

    restored = HarborSimulator(initial=snapshot)

    assert all(step.duration_minutes > 0 for step in restored.service_steps)
    bunker = next(
        step for step in restored.service_steps
        if step.kind == ServiceKind.BUNKER
    )
    tug = next(
        step for step in restored.service_steps
        if step.kind == ServiceKind.TUG
    )
    assert bunker.duration_minutes == 60
    assert tug.duration_minutes == 45


def test_compound_tug_bunker_recovery_links_incidents_and_preserves_lifecycle(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    tug_incident = sim.inject_incident(
        IncidentType.TUG_UNAVAILABLE,
        "pc-aurora",
        40,
    )
    bunker_incident = sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        45,
    )

    compound = [
        proposal
        for proposal in sim.generate_recovery_proposals(call_id="pc-aurora")
        if len(proposal.incident_ids) == 2
        and {
            action.service_kind
            for action in proposal.actions
            if action.service_kind is not None
        } >= {ServiceKind.TUG, ServiceKind.BUNKER}
    ]
    assert compound

    proposal = min(compound, key=lambda item: item.disruption_score)
    assert proposal.title == "Compound recovery: Tug 22 + Bunker Barge 9"
    assert set(proposal.incident_ids) == {tug_incident.id, bunker_incident.id}
    assert proposal.projected_blocked_services == 0

    receipt = sim.apply_recovery_proposal(
        proposal.id,
        approved_by="ops-compound",
        approved_role=OperatorRole.OPERATOR,
        approved_display_name="Compound Ops",
    )
    assert set(receipt.incident_ids) == {tug_incident.id, bunker_incident.id}
    assert receipt.resulting_blocked_services == 0

    active = {
        incident.id: incident.status.value
        for incident in sim.incidents
        if incident.id in {tug_incident.id, bunker_incident.id}
    }
    assert active == {
        tug_incident.id: "active",
        bunker_incident.id: "active",
    }

    for call_id in ("pc-aurora", "pc-glory"):
        graph = sim.dependency_graph(call_id)
        nodes = {node["kind"]: node for node in graph["nodes"]}
        assert nodes["tug"]["state"] != "blocked"
        assert nodes["bunker"]["state"] != "blocked"
        assert nodes["departure"]["state"] != "blocked"


def test_compound_recovery_generation_is_deterministic():
    def signature():
        sim = HarborSimulator()
        sim.inject_incident(IncidentType.TUG_UNAVAILABLE, "pc-aurora", 40)
        sim.inject_incident(IncidentType.BUNKER_UNAVAILABLE, "pc-aurora", 45)

        rows = []
        for proposal in sim.generate_recovery_proposals(call_id="pc-aurora"):
            if len(proposal.incident_ids) != 2:
                continue
            actions = tuple(
                (
                    action.action_type.value,
                    action.port_call_id,
                    action.service_kind.value if action.service_kind else None,
                    action.from_resource_id,
                    action.to_resource_id,
                    action.shift_minutes,
                )
                for action in proposal.actions
            )
            rows.append(
                (
                    proposal.title,
                    actions,
                    proposal.projected_total_delay_minutes,
                    proposal.projected_blocked_services,
                    proposal.disruption_score,
                )
            )
        return rows

    assert signature() == signature()


def test_recorded_duration_calibration_updates_steps_provenance_and_fingerprint(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        recovery_receipt_sink=store.save_recovery_receipt,
    )

    sim.inject_incident(IncidentType.BUNKER_UNAVAILABLE, "pc-aurora", 45)
    before = sim.generate_recovery_proposals(call_id="pc-aurora")[0]
    now = datetime.now(timezone.utc).replace(microsecond=0)

    calibration = ServiceDurationCalibration(
        service_kind=ServiceKind.BUNKER,
        duration_minutes=75,
        source_id="recorded-bunker-calibration",
        mode=DataSourceMode.RECORDED,
        provider="Terminal service history replay",
        observed_at=now,
        detail="Recorded median bunker-service duration.",
    )
    provenance = DataSourceProvenance(
        source_id=calibration.source_id,
        domain=DataDomain.SERVICE_CALIBRATION,
        mode=calibration.mode,
        provider=calibration.provider,
        observed_at=now,
        received_at=now,
        stale_after_seconds=86_400,
        health=AdapterHealth.HEALTHY,
        record_count=1,
        detail=calibration.detail,
    )

    updated = sim.set_service_duration_calibration(
        calibration,
        provenance,
        updated_by="operator-calibration",
        updated_role=OperatorRole.OPERATOR,
    )

    assert updated.duration_minutes == 75
    assert all(
        step.duration_minutes == 75
        for step in sim.service_steps
        if step.kind == ServiceKind.BUNKER
    )
    source = next(
        item for item in sim.data_sources
        if item.source_id == "recorded-bunker-calibration"
    )
    assert source.domain == DataDomain.SERVICE_CALIBRATION
    assert source.mode == DataSourceMode.RECORDED

    after = sim.generate_recovery_proposals(call_id="pc-aurora")[0]
    assert after.state_fingerprint != before.state_fingerprint
    assert after.decision_confidence.value == "medium"
    assert any(
        "Recorded replay data is active" in warning
        for warning in after.data_quality_warnings
    )

    event = next(
        item for item in sim.events
        if item.category == "service_calibration"
    )
    assert event.actor_id == "operator-calibration"
    assert event.actor_role == OperatorRole.OPERATOR
    assert event.source_id == "recorded-bunker-calibration"

    snapshot = store.load_snapshot()
    assert snapshot is not None
    restored = HarborSimulator(initial=snapshot)
    restored_calibration = next(
        item for item in restored.service_duration_calibrations
        if item.service_kind == ServiceKind.BUNKER
    )
    assert restored_calibration.duration_minutes == 75
    assert restored_calibration.source_id == "recorded-bunker-calibration"


def test_stale_duration_calibration_cannot_mutate_operational_truth():
    sim = HarborSimulator()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    before = [
        step.duration_minutes
        for step in sim.service_steps
        if step.kind == ServiceKind.BUNKER
    ]

    calibration = ServiceDurationCalibration(
        service_kind=ServiceKind.BUNKER,
        duration_minutes=90,
        source_id="stale-bunker-calibration",
        mode=DataSourceMode.RECORDED,
        provider="Expired terminal history",
        observed_at=now - timedelta(days=2),
    )
    provenance = DataSourceProvenance(
        source_id=calibration.source_id,
        domain=DataDomain.SERVICE_CALIBRATION,
        mode=calibration.mode,
        provider=calibration.provider,
        observed_at=calibration.observed_at,
        received_at=now,
        freshness_seconds=2 * 24 * 60 * 60,
        stale_after_seconds=60,
        stale=True,
        health=AdapterHealth.STALE,
        record_count=1,
    )

    try:
        sim.set_service_duration_calibration(calibration, provenance)
    except ValueError as exc:
        assert "not usable" in str(exc)
    else:
        raise AssertionError("stale calibration unexpectedly mutated operational state")

    after = [
        step.duration_minutes
        for step in sim.service_steps
        if step.kind == ServiceKind.BUNKER
    ]
    assert after == before
    assert not any(
        source.source_id == "stale-bunker-calibration"
        for source in sim.data_sources
    )


def test_pre_v015_snapshot_migrates_service_duration_calibration_state():
    sim = HarborSimulator()
    snapshot = sim.overview()
    snapshot.service_duration_calibrations = []
    snapshot.data_sources = [
        source for source in snapshot.data_sources
        if source.domain != DataDomain.SERVICE_CALIBRATION
    ]
    for step in snapshot.service_steps:
        step.duration_minutes = 0

    restored = HarborSimulator(initial=snapshot)

    assert len(restored.service_duration_calibrations) == len(ServiceKind)
    bunker = next(
        item for item in restored.service_duration_calibrations
        if item.service_kind == ServiceKind.BUNKER
    )
    assert bunker.duration_minutes == 60
    assert bunker.source_id == "synthetic-service-calibration"
    assert any(
        source.source_id == "synthetic-service-calibration"
        and source.domain == DataDomain.SERVICE_CALIBRATION
        for source in restored.data_sources
    )
    assert all(step.duration_minutes > 0 for step in restored.service_steps)


def test_failed_selected_recovery_resource_returns_ranked_contingency():
    sim = HarborSimulator()
    primary = sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        45,
    )
    initial = sim.generate_recovery_proposals(call_id="pc-aurora")
    stale = next(
        proposal
        for proposal in initial
        if any(
            action.to_resource_id == "bunker-barge-12"
            for action in proposal.actions
        )
    )

    alternate_failure = sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        0,
        target_resource_id="bunker-barge-12",
    )
    barge12 = next(
        resource
        for resource in sim.service_resources
        if resource.id == "bunker-barge-12"
    )
    assert barge12.status.value == "unavailable"

    aurora_bunker_before = next(
        step
        for step in sim.service_steps
        if step.port_call_id == "pc-aurora"
        and step.kind == ServiceKind.BUNKER
    )
    assert aurora_bunker_before.resource_id == "bunker-barge-4"

    try:
        sim.apply_recovery_proposal(
            stale.id,
            approved_by="contingency-operator",
            approved_role=OperatorRole.OPERATOR,
            approved_display_name="Contingency Operator",
        )
    except RecoveryProposalStaleError as exc:
        contingency = exc.contingency
    else:
        raise AssertionError("stale recovery plan unexpectedly applied")

    assert contingency.stale_proposal_id == stale.id
    assert contingency.target_port_call_id == "pc-aurora"
    assert contingency.stale_state_fingerprint == stale.state_fingerprint
    assert contingency.current_state_fingerprint != stale.state_fingerprint
    assert contingency.unavailable_resource_ids == ["bunker-barge-12"]
    assert contingency.auto_apply is False
    assert contingency.replacement_proposals
    assert all(
        action.to_resource_id != "bunker-barge-12"
        for proposal in contingency.replacement_proposals
        for action in proposal.actions
    )

    replacement = next(
        proposal
        for proposal in contingency.replacement_proposals
        if any(
            action.to_resource_id == "bunker-barge-9"
            for action in proposal.actions
        )
    )

    # Returning contingencies must not mutate the harbor by itself.
    aurora_bunker_still = next(
        step
        for step in sim.service_steps
        if step.port_call_id == "pc-aurora"
        and step.kind == ServiceKind.BUNKER
    )
    assert aurora_bunker_still.resource_id == "bunker-barge-4"

    receipt = sim.apply_recovery_proposal(
        replacement.id,
        approved_by="contingency-operator",
        approved_role=OperatorRole.OPERATOR,
        approved_display_name="Contingency Operator",
    )
    assert receipt.resulting_blocked_services == 0

    active_ids = {
        incident.id
        for incident in sim.incidents
        if incident.status.value == "active"
    }
    assert primary.id in active_ids
    assert alternate_failure.id in active_ids


def test_explicit_schema_migration_stamps_version_and_verify(tmp_path):
    store = OperationsStore(
        f"sqlite:///{tmp_path / 'schema-migration.db'}"
    )

    before = store.schema_status()
    assert before["database_reachable"] is True
    assert before["compatible"] is False
    assert before["current_version"] is None
    assert "schema_version" in before["missing_tables"]

    migrated = store.migrate_schema()
    assert migrated["compatible"] is True
    assert migrated["current_version"] == 3
    assert migrated["missing_tables"] == []

    verified = store.verify_schema()
    assert verified == migrated


def test_verify_schema_rejects_unmigrated_database(tmp_path):
    store = OperationsStore(
        f"sqlite:///{tmp_path / 'schema-unmigrated.db'}"
    )

    try:
        store.verify_schema()
    except RuntimeError as exc:
        assert "not compatible" in str(exc).lower()
    else:
        raise AssertionError("verify mode accepted an unmigrated database")


def test_schema_v1_migrates_additively_to_v3(tmp_path):
    store = OperationsStore(
        f"sqlite:///{tmp_path / 'schema-v1.db'}"
    )
    with store.engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE schema_version ("
            "id INTEGER PRIMARY KEY, "
            "version INTEGER NOT NULL, "
            "updated_at DATETIME NOT NULL)"
        ))
        connection.execute(
            text(
                "INSERT INTO schema_version "
                "(id, version, updated_at) "
                "VALUES (1, 1, :updated_at)"
            ),
            {"updated_at": datetime.now(timezone.utc)},
        )

    before = store.schema_status()
    assert before["current_version"] == 1
    assert before["compatible"] is False
    assert "recovery_proposal_evidence" in before["missing_tables"]
    assert "scenario_run_evidence" in before["missing_tables"]

    after = store.migrate_schema()
    assert after["compatible"] is True
    assert after["current_version"] == 3
    assert after["missing_tables"] == []


def test_recovery_evidence_restores_stale_contingency_after_restart(tmp_path):
    store = make_store(tmp_path)
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(
            store.replay_outbound_events(lambda event: True)
        ),
        pending_count=store.pending_outbound_count,
        recovery_receipt_sink=store.save_recovery_receipt,
        recovery_proposal_evidence_sink=store.save_recovery_proposal_evidence,
    )

    sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        45,
    )
    proposals = sim.generate_recovery_proposals(
        call_id="pc-aurora",
        evidence_trigger="test-planning",
    )
    stale = next(
        proposal
        for proposal in proposals
        if any(
            action.to_resource_id == "bunker-barge-12"
            for action in proposal.actions
        )
    )

    batches = store.list_recovery_proposal_evidence(limit=20)
    planning_batch = next(
        batch
        for batch in batches
        if batch.evidence_id
        and stale.id in [proposal.id for proposal in batch.proposals]
    )
    assert planning_batch.trigger == "test-planning"

    sim.inject_incident(
        IncidentType.BUNKER_UNAVAILABLE,
        "pc-aurora",
        0,
        target_resource_id="bunker-barge-12",
    )

    snapshot = store.load_snapshot()
    assert snapshot is not None

    stored_batches = store.list_recovery_proposal_evidence(limit=200)
    proposal_history = [
        proposal
        for batch in reversed(stored_batches)
        for proposal in batch.proposals
    ]
    restarted = HarborSimulator(
        initial=snapshot,
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        recovery_receipt_sink=store.save_recovery_receipt,
        recovery_proposal_evidence_sink=store.save_recovery_proposal_evidence,
        proposal_history=proposal_history,
    )

    try:
        restarted.apply_recovery_proposal(
            stale.id,
            approved_by="restart-operator",
            approved_role=OperatorRole.OPERATOR,
            approved_display_name="Restart Operator",
        )
    except RecoveryProposalStaleError as exc:
        contingency = exc.contingency
    else:
        raise AssertionError(
            "Restarted simulator must recover stale proposal context"
        )

    assert contingency.stale_proposal_id == stale.id
    assert contingency.unavailable_resource_ids == ["bunker-barge-12"]
    assert any(
        any(
            action.to_resource_id == "bunker-barge-9"
            for action in proposal.actions
        )
        for proposal in contingency.replacement_proposals
    )

    contingency_batches = store.list_recovery_proposal_evidence(limit=20)
    linked = next(
        batch
        for batch in contingency_batches
        if batch.stale_parent_proposal_id == stale.id
    )
    assert linked.trigger == "contingency"

    store.clear_demo_state()
    retained = store.list_recovery_proposal_evidence(limit=20)
    assert any(batch.evidence_id == planning_batch.evidence_id for batch in retained)
    assert any(batch.evidence_id == linked.evidence_id for batch in retained)


def test_database_url_normalizes_postgres_to_psycopg_driver():
    assert normalize_database_url(
        "postgres://user:pass@example.invalid:5432/portflow"
    ) == "postgresql+psycopg://user:pass@example.invalid:5432/portflow"
    assert normalize_database_url(
        "postgresql://user:pass@example.invalid:5432/portflow?sslmode=require"
    ) == (
        "postgresql+psycopg://user:pass@example.invalid:5432/"
        "portflow?sslmode=require"
    )
    assert normalize_database_url(
        "postgresql+psycopg://user:pass@example.invalid/portflow"
    ) == "postgresql+psycopg://user:pass@example.invalid/portflow"


def test_schema_v2_migrates_additively_to_v3(tmp_path):
    store = OperationsStore(
        f"sqlite:///{tmp_path / 'schema-v2.db'}"
    )
    with store.engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE schema_version ("
            "id INTEGER PRIMARY KEY, "
            "version INTEGER NOT NULL, "
            "updated_at DATETIME NOT NULL)"
        ))
        connection.execute(
            text(
                "INSERT INTO schema_version "
                "(id, version, updated_at) "
                "VALUES (1, 2, :updated_at)"
            ),
            {"updated_at": datetime.now(timezone.utc)},
        )

    before = store.schema_status()
    assert before["current_version"] == 2
    assert before["compatible"] is False
    assert "vessel_runtime_event" in before["missing_tables"]

    after = store.migrate_schema()
    assert after["compatible"] is True
    assert after["current_version"] == 3
    assert after["missing_tables"] == []

    with store.engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table'"
                )
            )
        }
    assert "vessel_runtime_event" in tables
