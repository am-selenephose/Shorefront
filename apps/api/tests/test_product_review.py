"""Regression checks from the operational integration review, using disposable data."""
import json
import os
import subprocess
import sys

from sqlalchemy import update

from test_product import activate, customer, headers, invite, preview, setup_call, write


def approve(client, packet):
    result = client.post(f"/api/v1/decisions/{packet['id']}/approve", headers=headers(client),
                         json={'option_id':'option-0', 'reason':'Reviewed recorded facts'})
    assert result.status_code == 200, result.text


def test_migrator_refuses_unknown_runtime_without_creating_training_database(tmp_path):
    path = tmp_path / 'wrong-mode.db'
    result = subprocess.run([sys.executable, '-m', 'shorefront_api.migrate'], capture_output=True, text=True,
        timeout=30, env={**os.environ, 'DATABASE_URL':f'sqlite:///{path}', 'SHOREFRONT_RUNTIME_MODE':'typo'})
    assert result.returncode != 0
    assert 'RUNTIME_MODE must be' in result.stderr
    assert not path.exists()


def test_outcome_cannot_schedule_a_second_effective_record_or_change_decision(customer):
    setup_call(customer)
    supervisor = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    first = preview(customer)
    approve(supervisor, first)
    second = preview(customer)
    approve(supervisor, second)
    body = {'decision_id':first['id'], 'actual_arrival':'2026-01-05T10:00:00Z', 'actual_departure':'2026-01-05T15:00:00Z'}
    assert write(customer, 'outcome', 'scheduled', body, valid_at='2099-01-01T00:00:00Z').status_code == 422
    assert write(customer, 'outcome', 'observed', body).status_code == 201
    assert write(customer, 'outcome', 'duplicate', body).status_code == 409
    assert write(customer, 'outcome', 'observed', {**body, 'decision_id':second['id']}, revision=1).status_code == 409
    assert customer.get('/api/v1/outcomes').json()['sample_count'] == 1


def test_outcome_decision_binding_is_immutable(customer):
    setup_call(customer)
    supervisor = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    first = preview(customer)
    approve(supervisor, first)
    second = preview(customer)
    approve(supervisor, second)
    body = {'decision_id':first['id'], 'actual_arrival':'2026-01-05T10:00:00Z', 'actual_departure':'2026-01-05T15:00:00Z'}
    assert write(customer, 'outcome', 'observed', body).status_code == 201
    assert write(customer, 'outcome', 'observed', {**body, 'decision_id':second['id']}, revision=1).status_code == 409


def test_decision_approval_refuses_corrupted_packet_and_leaves_plan_unchanged(customer):
    from shorefront_api.product_decisions import packets
    setup_call(customer)
    supervisor = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    packet = preview(customer)
    before = customer.get('/api/v1/workspace').json()['records']
    packet['options'][0]['call_payload']['etd'] = '2026-10-05T23:00:00Z'
    with customer.app.state.product_store.transaction() as connection:
        connection.execute(update(packets).where(packets.c.id == packet['id']).values(payload=json.dumps(packet)))
    response = supervisor.post(f"/api/v1/decisions/{packet['id']}/approve", headers=headers(supervisor),
                               json={'option_id':'option-0','reason':'Review cannot authorize corrupted evidence'})
    assert response.status_code == 409
    assert 'integrity' in response.json()['detail'].lower()
    assert customer.get('/api/v1/workspace').json()['records'] == before
