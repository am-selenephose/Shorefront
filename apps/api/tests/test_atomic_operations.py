"""Fault injection against local temporary state, never live integrations."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import event

import shorefront_api.main as api
from shorefront_api.models import IncidentType, IntegrationIdentity, LinkMode, OperatorIdentity, OperatorRole, VesselRuntimeEvent
from shorefront_api.storage import OperationsStore

OPERATOR = OperatorIdentity(operator_id='atomic-test', display_name='Atomic test', role=OperatorRole.OPERATOR)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    store = OperationsStore(f'sqlite:///{tmp_path}/atomic.db')
    store.init_schema()
    monkeypatch.setattr(api, 'store', store)
    monkeypatch.setattr(api, 'sim', api.build_simulator())
    api.run_scenario('tug-loss')
    api.connectivity(api.ConnectivityRequest(mode=LinkMode.OFFLINE_EDGE))
    yield store
    store.engine.dispose()


def picture():
    state = api.sim.overview().model_dump(mode='json', exclude={'generated_at'})
    return state, api.sim.tick_count, api.sim.rng.getstate(), deepcopy(api.sim._proposal_history)


def durable(store):
    return [
        store.load_snapshot(), store.list_events(), store.list_incidents(),
        store.list_recovery_receipts(), store.list_recovery_proposal_evidence(),
        store.pending_outbound_events(), store.list_replay_receipts(),
        store.list_scenario_run_evidence(), store.list_vessel_runtime_events(),
    ]


@pytest.mark.parametrize('sink', ['recovery_receipt_sink', 'event_sink', 'spool_sink', 'snapshot_sink'])
def test_apply_rolls_back_every_record_and_memory_when_a_sink_fails(runtime, monkeypatch, sink):
    proposal = api.recovery_proposals()['proposals'][0]
    before_memory, before_db = picture(), durable(runtime)
    original = getattr(api.sim, sink)

    def fail_after_write(value):
        original(value)
        raise RuntimeError(f'injected {sink} failure')

    monkeypatch.setattr(api.sim, sink, fail_after_write)
    with pytest.raises(RuntimeError, match='injected'):
        api.apply_recovery_proposal(proposal.id, OPERATOR)
    assert picture() == before_memory
    assert durable(runtime) == before_db
    monkeypatch.setattr(api.sim, sink, original)
    receipt = api.apply_recovery_proposal(proposal.id, OPERATOR)
    assert receipt.proposal_id == proposal.id
    assert len(runtime.list_recovery_receipts()) == 1
    assert runtime.load_snapshot().port_calls == api.sim.port_calls


def test_failed_incident_rolls_back_its_incident_row_and_memory(runtime, monkeypatch):
    before_memory, before_db = picture(), durable(runtime)
    original = api.sim.incident_sink

    def fail_incident(value):
        original(value)
        raise RuntimeError('injected incident write failure')

    monkeypatch.setattr(api.sim, 'incident_sink', fail_incident)
    with pytest.raises(RuntimeError, match='incident write failure'):
        api.create_incident(api.IncidentRequest(incident_type=IncidentType.PILOT_DELAY, target_port_call_id='pc-aurora'), OPERATOR)
    assert picture() == before_memory
    assert durable(runtime) == before_db


def test_failed_replay_restores_pending_envelopes_and_acknowledgements(runtime, monkeypatch):
    assert runtime.pending_outbound_count() > 0
    before_memory, before_db = picture(), durable(runtime)

    def fail_snapshot(value):
        raise RuntimeError('injected replay snapshot failure')

    monkeypatch.setattr(api.sim, 'snapshot_sink', fail_snapshot)
    with pytest.raises(RuntimeError, match='replay snapshot failure'):
        api.replay_now()
    assert picture() == before_memory
    assert durable(runtime) == before_db


def test_tick_failure_restores_rng_tick_and_events(runtime, monkeypatch):
    api.sim.tick_count = 11
    before_memory, before_db = picture(), durable(runtime)

    def fail_snapshot(value):
        raise RuntimeError('injected tick failure')

    monkeypatch.setattr(api.sim, 'snapshot_sink', fail_snapshot)
    with pytest.raises(RuntimeError, match='tick failure'):
        api.tick_runtime()
    assert picture() == before_memory
    assert durable(runtime) == before_db


def test_unit_of_work_reads_own_writes_and_cleans_up_after_rollback(runtime, tmp_path):
    other = OperationsStore(f'sqlite:///{tmp_path}/independent.db')
    other.init_schema()
    event = api.sim.events[-1].model_copy(update={'id': 'independent-uow-event'})
    try:
        with pytest.raises(RuntimeError, match='abort unit'):
            with runtime.transaction():
                assert runtime.append_event(event)
                assert any(item.id == event.id for item in runtime.list_events())
                assert runtime.queue_outbound_event(event)
                assert any(item.id == event.id for item in runtime.pending_outbound_events())
                assert other.append_event(event)  # Different store commits independently.
                raise RuntimeError('abort unit')
        assert not any(item.id == event.id for item in runtime.list_events())
        assert not any(item.id == event.id for item in runtime.pending_outbound_events())
        assert any(item.id == event.id for item in other.list_events())
        assert runtime.append_event(event)  # No leaked failed transaction.
        assert any(item.id == event.id for item in runtime.list_events())
    finally:
        other.engine.dispose()


def test_final_commit_failure_restores_in_memory_state_and_all_rows(runtime):
    proposal = api.recovery_proposals()['proposals'][0]
    before_memory, before_db = picture(), durable(runtime)
    approvals_before = api.metrics.counter('portflow_recovery_approvals_total')

    def fail_commit(connection):
        raise RuntimeError('injected commit failure')

    event.listen(runtime.engine, 'commit', fail_commit)
    try:
        with pytest.raises(RuntimeError, match='injected commit failure'):
            api.apply_recovery_proposal(proposal.id, OPERATOR)
    finally:
        event.remove(runtime.engine, 'commit', fail_commit)
    assert picture() == before_memory
    assert durable(runtime) == before_db
    assert api.metrics.counter('portflow_recovery_approvals_total') == approvals_before


def test_failed_reset_restores_prior_simulator_and_durable_state(runtime, monkeypatch):
    previous = api.sim
    before_memory, before_db = picture(), durable(runtime)
    original = runtime.save_snapshot

    def fail_snapshot(value):
        original(value)
        raise RuntimeError('reset failed')

    monkeypatch.setattr(runtime, 'save_snapshot', fail_snapshot)
    with pytest.raises(RuntimeError, match='reset failed'):
        api.reset_demo()
    assert api.sim is previous
    assert picture() == before_memory
    assert durable(runtime) == before_db


def test_readers_do_not_observe_a_half_applied_recovery(runtime, monkeypatch):
    proposal = api.recovery_proposals()['proposals'][0]
    entered, release, reader_started, reader_done = (Event() for _ in range(4))
    original = api.sim.recovery_receipt_sink

    def pause_receipt(value):
        result = original(value)
        entered.set()
        assert release.wait(5), 'test release timed out'
        return result

    def read_picture():
        reader_started.set()
        result = api.harbor()
        reader_done.set()
        return result

    monkeypatch.setattr(api.sim, 'recovery_receipt_sink', pause_receipt)
    with ThreadPoolExecutor(max_workers=2) as pool:
        apply = pool.submit(api.apply_recovery_proposal, proposal.id, OPERATOR)
        assert entered.wait(5)
        read = pool.submit(read_picture)
        try:
            assert reader_started.wait(5)
            assert not reader_done.wait(.1), 'reader observed an uncommitted mutation'
        finally:
            release.set()
        receipt = apply.result(timeout=5)
        assert read.result(timeout=5).port_calls == runtime.load_snapshot().port_calls
        assert receipt.proposal_id == proposal.id


def test_concurrent_approval_has_one_committed_receipt(runtime):
    proposal = api.recovery_proposals()['proposals'][0]

    def approve():
        try:
            return api.apply_recovery_proposal(proposal.id, OPERATOR)
        except HTTPException as exc:
            assert exc.status_code == 409
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(runtime.list_recovery_receipts()) == 1
    assert runtime.load_snapshot().port_calls == api.sim.port_calls


def test_vessel_event_and_audit_are_atomic_and_retry_is_not_duplicate(runtime, monkeypatch):
    event = VesselRuntimeEvent(
        contract_version='portflow.vessel-event.v1', event_id='atomic-vessel-event',
        occurred_at=datetime.now(timezone.utc), vessel_id='v-aurora', port_call_id='pc-aurora',
        event_type='readiness', sequence=1, source_system='isolated-test', payload={'navigation_ready': True},
    )
    identity = IntegrationIdentity(integration_id='atomic-integration', display_name='Test integration', vessel_ids=['v-aurora'])
    before_db = durable(runtime)
    original = runtime.append_event

    def fail_audit(value):
        original(value)
        raise RuntimeError('injected vessel audit failure')

    monkeypatch.setattr(runtime, 'append_event', fail_audit)
    with pytest.raises(RuntimeError, match='vessel audit failure'):
        api.ingest_vessel_runtime_event(event, identity)
    assert durable(runtime) == before_db
    monkeypatch.setattr(runtime, 'append_event', original)
    receipt = api.ingest_vessel_runtime_event(event, identity)
    assert receipt.duplicate is False
    assert api.ingest_vessel_runtime_event(event, identity).duplicate is True
    assert sum(row.id == f'vessel-runtime-{event.event_id}' for row in runtime.list_events()) == 1


def test_scenario_evidence_failure_restores_old_picture_and_store(runtime, monkeypatch):
    previous = api.sim
    before_memory, before_db = picture(), durable(runtime)
    original = runtime.save_scenario_run_evidence

    def fail_evidence(value):
        original(value)
        raise RuntimeError('injected scenario evidence failure')

    monkeypatch.setattr(runtime, 'save_scenario_run_evidence', fail_evidence)
    with pytest.raises(RuntimeError, match='scenario evidence failure'):
        api.run_scenario('tug-loss')
    assert api.sim is previous
    assert picture() == before_memory
    assert durable(runtime) == before_db


def test_stale_apply_commits_new_planning_evidence_but_no_receipt(runtime):
    proposal = api.recovery_proposals()['proposals'][0]
    api.sim.service_resources[0].capacity += 1
    with pytest.raises(HTTPException) as conflict:
        api.apply_recovery_proposal(proposal.id, OPERATOR)
    assert conflict.value.status_code == 409
    assert conflict.value.detail['code'] == 'recovery_proposal_stale'
    assert any(row.trigger == 'contingency' and row.stale_parent_proposal_id == proposal.id
               for row in runtime.list_recovery_proposal_evidence())
    assert runtime.list_recovery_receipts() == []


def test_api_response_does_not_retain_live_model_references(runtime):
    response = api.create_incident(api.IncidentRequest(
        incident_type=IncidentType.PILOT_DELAY, target_port_call_id='pc-aurora',
    ), OPERATOR)
    resolved = api.resolve_incident(response.id, OPERATOR)
    assert resolved.status.value == 'resolved'
    assert response.status.value == 'active'
    assert next(row for row in runtime.list_incidents() if row.id == response.id).status.value == 'resolved'


def test_cancelled_shutdown_waits_for_inflight_tick_thread(runtime, monkeypatch):
    started, release, finished = Event(), Event(), Event()
    monkeypatch.setattr(api, 'initialize_runtime', lambda: None)

    def blocked_tick():
        started.set()
        assert release.wait(5)
        finished.set()

    monkeypatch.setattr(api, 'tick_runtime', blocked_tick)

    async def exercise():
        end_context = asyncio.Event()

        async def lifetime():
            async with api.lifespan(api.app):
                await end_context.wait()

        lifetime_task = asyncio.create_task(lifetime())
        assert await asyncio.to_thread(started.wait, 5)
        end_context.set()
        await asyncio.sleep(0)  # Enter shutdown's join of the running tick.
        lifetime_task.cancel()
        try:
            done, _ = await asyncio.wait({lifetime_task}, timeout=.05)
            assert not done, 'lifespan exited while the worker still owned state'
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await lifetime_task
        assert finished.is_set()

    asyncio.run(exercise())
