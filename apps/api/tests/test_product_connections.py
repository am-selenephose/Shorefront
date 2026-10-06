from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from shorefront_api.product_store import connection_sources, partner_grants
from test_product import BOOTSTRAP, ORIGIN, PASSWORD, activate, bootstrap, build_app, headers, invite, setup_call, write


@pytest.fixture
def connected(tmp_path):
    app = build_app(tmp_path / 'connections.db')
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        yield client


def create_source(client, source_id='terminal-feed', allowed=None, hours=24):
    response = client.post('/api/v1/connections/sources', headers=headers(client), json={
        'id': source_id,
        'name': 'Terminal operating feed',
        'allowed_kinds': allowed or ['port', 'berth', 'vessel', 'call', 'incident', 'task'],
        'expires_in_hours': hours,
    })
    assert response.status_code == 201, response.text
    return response.json()


def create_grant(client, grant_id='agent-window', call_ids=None):
    response = client.post('/api/v1/connections/partner-grants', headers=headers(client), json={
        'id': grant_id,
        'name': 'Agent call window',
        'allowed_kinds': ['port', 'berth', 'vessel', 'call', 'incident'],
        'fields': {
            'port': ['name'],
            'berth': ['name', 'port_id'],
            'vessel': ['name', 'imo'],
            'call': ['vessel_id', 'berth_id', 'eta', 'etd', 'status'],
            'incident': ['title', 'call_id', 'severity', 'status'],
        },
        'call_ids': call_ids or [],
        'expires_in_hours': 24,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_source_token_is_one_time_digest_and_ingests_atomic_records(connected):
    created = create_source(connected)
    token = created['token']
    assert len(token) >= 32
    assert created['source']['write_count'] == 0
    listing = connected.get('/api/v1/connections/sources').json()
    assert listing[0]['id'] == 'terminal-feed'
    assert 'token' not in listing[0]

    with connected.app.state.product_store.transaction() as connection:
        row = connection.execute(select(connection_sources).where(connection_sources.c.id == 'terminal-feed')).mappings().one()
        assert row['digest'] != token
        assert token not in row['digest']

    batch = {
        'records': [
            {'kind': 'port', 'record_id': 'feed-port', 'expected_revision': 0,
             'payload': {'name': 'Feed Port', 'timezone': 'UTC'}},
            {'kind': 'berth', 'record_id': 'feed-berth', 'expected_revision': 0,
             'payload': {'name': 'Feed Berth', 'port_id': 'feed-port'}},
            {'kind': 'vessel', 'record_id': 'feed-vessel', 'expected_revision': 0,
             'payload': {'name': 'Feed Vessel', 'imo': '1234567'}},
            {'kind': 'call', 'record_id': 'feed-call', 'expected_revision': 0,
             'payload': {'vessel_id': 'feed-vessel', 'berth_id': 'feed-berth',
                         'eta': '2026-10-07T10:00:00Z', 'etd': '2026-10-07T15:00:00Z'}},
        ],
    }
    auth = {'Authorization': f'Bearer {token}', 'Idempotency-Key': 'source-batch-1'}
    first = connected.post('/api/v1/integrations/terminal-feed/records', headers=auth, json=batch)
    assert first.status_code == 201, first.text
    assert [record['kind'] for record in first.json()['records']] == ['port', 'berth', 'vessel', 'call']
    assert all(record['source'] == 'integration:terminal-feed' for record in first.json()['records'])
    assert all(record['actor_id'] == 'integration:terminal-feed' for record in first.json()['records'])

    replay = connected.post('/api/v1/integrations/terminal-feed/records', headers=auth, json=batch)
    assert replay.status_code == 201
    assert replay.json() == first.json()
    after = connected.get('/api/v1/connections/sources').json()[0]
    assert after['write_count'] == 4
    assert after['last_used_at']

    workspace = connected.get('/api/v1/workspace').json()['records']
    assert len([record for record in workspace if record['record_id'].startswith('feed-')]) == 4


def test_source_scope_auth_revoke_and_atomic_rollback(connected):
    created = create_source(connected, allowed=['vessel'])
    token = created['token']
    good_headers = {'Authorization': f'Bearer {token}', 'Idempotency-Key': 'scoped-batch'}
    forbidden = connected.post('/api/v1/integrations/terminal-feed/records', headers=good_headers, json={'records': [
        {'kind': 'vessel', 'record_id': 'would-rollback', 'expected_revision': 0, 'payload': {'name': 'Rollback Vessel'}},
        {'kind': 'port', 'record_id': 'forbidden-port', 'expected_revision': 0, 'payload': {'name': 'No', 'timezone': 'UTC'}},
    ]})
    assert forbidden.status_code == 403
    assert not any(record['record_id'] == 'would-rollback' for record in connected.get('/api/v1/workspace').json()['records'])

    assert connected.post('/api/v1/integrations/terminal-feed/records',
                          headers={'Authorization': 'Bearer wrong', 'Idempotency-Key': 'bad'}, json={'records': [
                              {'kind': 'vessel', 'record_id': 'x', 'expected_revision': 0, 'payload': {'name': 'X'}}
                          ]}).status_code == 401
    assert connected.post('/api/v1/connections/sources/terminal-feed/revoke', headers=headers(connected), json={}).status_code == 200
    assert connected.post('/api/v1/integrations/terminal-feed/records', headers=good_headers, json={'records': [
        {'kind': 'vessel', 'record_id': 'after-revoke', 'expected_revision': 0, 'payload': {'name': 'No'}}
    ]}).status_code == 401


def test_only_admin_manages_sources_and_partner_grants(connected):
    operator_token = invite(connected, 'operator')
    operator = activate(connected.app, operator_token, 'operator')
    try:
        assert operator.post('/api/v1/connections/sources', headers=headers(operator), json={
            'id': 'nope', 'name': 'Nope', 'allowed_kinds': ['vessel'], 'expires_in_hours': 24,
        }).status_code == 403
        assert operator.get('/api/v1/connections/sources').status_code == 403
        assert operator.post('/api/v1/connections/partner-grants', headers=headers(operator), json={
            'id': 'nope', 'name': 'Nope', 'allowed_kinds': ['vessel'],
            'fields': {'vessel': ['name']}, 'call_ids': [], 'expires_in_hours': 24,
        }).status_code == 403
    finally:
        operator.close()


def test_partner_projection_is_field_scoped_and_call_scoped(connected):
    setup_call(connected)
    assert write(connected, 'incident', 'incident-one', {
        'title': 'Pilot late', 'call_id': 'call-one', 'severity': 'high', 'detail': 'internal detail',
    }).status_code == 201
    assert write(connected, 'vessel', 'other-vessel', {'name': 'Other Vessel', 'imo': '7654321'}).status_code == 201
    assert write(connected, 'call', 'other-call', {
        'vessel_id': 'other-vessel', 'berth_id': 'berth-one',
        'eta': '2026-10-08T10:00:00Z', 'etd': '2026-10-08T15:00:00Z',
    }).status_code == 201

    created = create_grant(connected, call_ids=['call-one'])
    token = created['token']
    projection = connected.get('/api/v1/partner/projection', headers={'Authorization': f'Bearer {token}'})
    assert projection.status_code == 200, projection.text
    body = projection.json()
    assert body['grant']['id'] == 'agent-window'
    ids = {(record['kind'], record['record_id']) for record in body['records']}
    assert ('call', 'call-one') in ids
    assert ('call', 'other-call') not in ids
    assert ('vessel', 'vessel-one') in ids
    assert ('vessel', 'other-vessel') not in ids
    assert ('berth', 'berth-one') in ids
    assert ('port', 'port-one') in ids
    assert ('incident', 'incident-one') in ids

    incident = next(record for record in body['records'] if record['record_id'] == 'incident-one')
    assert incident['payload'] == {'title': 'Pilot late', 'call_id': 'call-one', 'severity': 'high', 'status': 'open'}
    assert 'source' not in incident and 'actor_id' not in incident
    vessel = next(record for record in body['records'] if record['record_id'] == 'vessel-one')
    assert set(vessel['payload']) <= {'name', 'imo'}

    grants = connected.get('/api/v1/connections/partner-grants').json()
    assert grants[0]['access_count'] == 1
    assert grants[0]['last_used_at']
    assert 'token' not in grants[0]


def test_partner_projection_revoke_and_invalid_field_rules_fail_closed(connected):
    setup_call(connected)
    invalid = connected.post('/api/v1/connections/partner-grants', headers=headers(connected), json={
        'id': 'invalid-fields', 'name': 'Invalid', 'allowed_kinds': ['vessel'],
        'fields': {'vessel': ['name', 'password']}, 'call_ids': [], 'expires_in_hours': 24,
    })
    assert invalid.status_code == 422

    created = create_grant(connected)
    token = created['token']
    assert connected.get('/api/v1/partner/projection', headers={'Authorization': f'Bearer {token}'}).status_code == 200
    assert connected.post('/api/v1/connections/partner-grants/agent-window/revoke', headers=headers(connected), json={}).status_code == 200
    assert connected.get('/api/v1/partner/projection', headers={'Authorization': f'Bearer {token}'}).status_code == 401


def test_connection_tables_require_explicit_migration_for_verify_mode(tmp_path):
    app = build_app(tmp_path / 'old.db')
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
    store = app.state.product_store
    # Simulate an existing pre-feature installation by dropping only the additive connection tables.
    with store.engine.begin() as connection:
        partner_grants.drop(connection)
        connection_sources.drop(connection)
    with pytest.raises(RuntimeError, match='schema is missing'):
        store.initialize(migrate=False)
    store.initialize(migrate=True)
    store.initialize(migrate=False)
    store.engine.dispose()


def test_rotated_credentials_invalidate_old_tokens_and_expired_tokens_fail_closed(connected):
    setup_call(connected)
    source = create_source(connected)
    old_source_token = source['token']
    rotated = connected.post('/api/v1/connections/sources/terminal-feed/rotate?expires_in_hours=24',
                             headers=headers(connected), json={})
    assert rotated.status_code == 201, rotated.text
    new_source_token = rotated.json()['token']
    assert new_source_token != old_source_token
    payload = {'records': [
        {'kind': 'vessel', 'record_id': 'rotate-vessel', 'expected_revision': 0,
         'payload': {'name': 'Rotated Feed Vessel'}},
    ]}
    assert connected.post('/api/v1/integrations/terminal-feed/records',
                          headers={'Authorization': f'Bearer {old_source_token}', 'Idempotency-Key': 'old-source'},
                          json=payload).status_code == 401
    assert connected.post('/api/v1/integrations/terminal-feed/records',
                          headers={'Authorization': f'Bearer {new_source_token}', 'Idempotency-Key': 'new-source'},
                          json=payload).status_code == 201

    grant = create_grant(connected)
    old_grant_token = grant['token']
    rotated_grant = connected.post('/api/v1/connections/partner-grants/agent-window/rotate?expires_in_hours=24',
                                   headers=headers(connected), json={})
    assert rotated_grant.status_code == 201, rotated_grant.text
    new_grant_token = rotated_grant.json()['token']
    assert new_grant_token != old_grant_token
    assert connected.get('/api/v1/partner/projection',
                         headers={'Authorization': f'Bearer {old_grant_token}'}).status_code == 401
    assert connected.get('/api/v1/partner/projection',
                         headers={'Authorization': f'Bearer {new_grant_token}'}).status_code == 200

    past = '2000-01-01T00:00:00.000000+00:00'
    with connected.app.state.product_store.transaction() as connection:
        connection.execute(update(connection_sources).where(connection_sources.c.id == 'terminal-feed').values(expires_at=past))
        connection.execute(update(partner_grants).where(partner_grants.c.id == 'agent-window').values(expires_at=past))
    assert connected.post('/api/v1/integrations/terminal-feed/records',
                          headers={'Authorization': f'Bearer {new_source_token}', 'Idempotency-Key': 'expired-source'},
                          json={'records': [
                              {'kind': 'vessel', 'record_id': 'expired-vessel', 'expected_revision': 0,
                               'payload': {'name': 'No'}}
                          ]}).status_code == 401
    assert connected.get('/api/v1/partner/projection',
                         headers={'Authorization': f'Bearer {new_grant_token}'}).status_code == 401


def test_unknown_call_scope_is_rejected_instead_of_broadening_projection(connected):
    setup_call(connected)
    response = connected.post('/api/v1/connections/partner-grants', headers=headers(connected), json={
        'id': 'missing-call-scope', 'name': 'Bad scope',
        'allowed_kinds': ['call'], 'fields': {'call': ['status']},
        'call_ids': ['does-not-exist'], 'expires_in_hours': 24,
    })
    assert response.status_code == 422
    assert connected.get('/api/v1/connections/partner-grants').json() == []
