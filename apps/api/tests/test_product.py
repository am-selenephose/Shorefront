"""Customer workflows, against real HTTP handlers and isolated durable storage."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

ORIGIN = 'https://shorefront.test'
BOOTSTRAP = 'local-test-bootstrap-token-never-for-production'
PASSWORD = 'a long test-only passphrase 42'


def build_app(path, **kwargs):
    from shorefront_api.product_api import create_product_app
    return create_product_app(database_url=f'sqlite:///{path}', installation_id='customer-a',
                              origin=ORIGIN, bootstrap_token=BOOTSTRAP, **kwargs)


def bootstrap(client):
    response = client.post('/api/v1/auth/bootstrap', headers={'Origin': ORIGIN}, json={
        'bootstrap_token': BOOTSTRAP, 'email': 'owner@example.test',
        'display_name': 'Port Owner', 'password': PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def customer(tmp_path):
    with TestClient(build_app(tmp_path / 'product.db'), base_url=ORIGIN) as client:
        bootstrap(client)
        yield client


def headers(client, key=None):
    me = client.get('/api/v1/auth/me')
    assert me.status_code == 200, me.text
    return {'Origin': ORIGIN, 'X-CSRF-Token': me.json()['csrf_token'],
            'Idempotency-Key': key or str(uuid4())}


def write(client, kind, record_id, payload, revision=0, key=None, valid_at=None):
    body = {'record_id': record_id, 'expected_revision': revision, 'source': 'operator entry', 'payload': payload}
    if valid_at:
        body['valid_at'] = valid_at
    return client.post(f'/api/v1/records/{kind}', headers=headers(client, key), json=body)


def setup_call(client):
    for kind, record_id, payload in [
        ('port', 'port-one', {'name': 'Customer Harbor', 'timezone': 'Asia/Karachi'}),
        ('berth', 'berth-one', {'name': 'North Quay', 'port_id': 'port-one', 'max_length_m': 250}),
        ('vessel', 'vessel-one', {'name': 'Customer Vessel', 'length_m': 200}),
        ('call', 'call-one', {'vessel_id': 'vessel-one', 'berth_id': 'berth-one',
                              'eta': '2026-10-05T10:00:00Z', 'etd': '2026-10-05T15:00:00Z'})]:
        response = write(client, kind, record_id, payload)
        assert response.status_code == 201, response.text


def invite(client, role='operator'):
    response = client.post('/api/v1/auth/invitations', headers=headers(client), json={
        'email': f'{role}@example.test', 'role': role})
    assert response.status_code == 201, response.text
    return response.json()['invitation_token']


def activate(app, token, role='operator'):
    other = TestClient(app, base_url=ORIGIN)
    response = other.post('/api/v1/auth/accept', headers={'Origin': ORIGIN}, json={
        'invitation_token': token, 'email': f'{role}@example.test',
        'display_name': role.title(), 'password': PASSWORD})
    assert response.status_code == 201, response.text
    return other


def test_new_customer_starts_empty_and_training_routes_are_absent(customer):
    workspace = customer.get('/api/v1/workspace').json()
    assert workspace['records'] == []
    assert workspace['runtime_mode'] == 'operational'
    assert customer.post('/api/v1/demo/reset', headers=headers(customer)).status_code == 404
    assert customer.get('/api/v1/harbor').status_code == 404


def test_bootstrap_is_single_use_and_secret_required(tmp_path):
    with TestClient(build_app(tmp_path / 'p.db'), base_url=ORIGIN) as client:
        body = {'bootstrap_token': 'wrong', 'email': 'owner@example.test', 'display_name': 'Owner', 'password': PASSWORD}
        assert client.post('/api/v1/auth/bootstrap', json=body, headers={'Origin': ORIGIN}).status_code == 403
        bootstrap(client)
        body['bootstrap_token'] = BOOTSTRAP
        assert client.post('/api/v1/auth/bootstrap', json=body, headers={'Origin': ORIGIN}).status_code == 409


@pytest.mark.parametrize('path', ['/api/v1/workspace', '/api/v1/history', '/api/v1/evidence', '/api/v1/team', '/api/v1/graph'])
def test_operational_reads_require_login(customer, path):
    customer.cookies.clear()
    assert customer.get(path).status_code == 401


def test_cookie_and_mutation_protection(customer):
    response = customer.post('/api/v1/auth/login', headers={'Origin': ORIGIN}, json={
        'email': 'owner@example.test', 'password': PASSWORD})
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie and 'samesite=strict' in cookie
    body = {'record_id': 'p', 'expected_revision': 0, 'source': 'manual', 'payload': {'name': 'P', 'timezone': 'UTC'}}
    assert customer.post('/api/v1/records/port', json=body).status_code == 403
    bad = headers(customer)
    bad['Origin'] = 'https://untrusted.test'
    assert customer.post('/api/v1/records/port', json=body, headers=bad).status_code == 403
    bad = headers(customer)
    bad['X-CSRF-Token'] = 'wrong'
    assert customer.post('/api/v1/records/port', json=body, headers=bad).status_code == 403


def test_records_idempotency_conflicts_and_audit(customer):
    setup_call(customer)
    payload = {'title': 'Tug unavailable', 'call_id': 'call-one', 'severity': 'high'}
    first = write(customer, 'incident', 'incident-one', payload, key='repeat-safe')
    assert first.status_code == 201, first.text
    replay = write(customer, 'incident', 'incident-one', payload, key='repeat-safe')
    assert replay.json() == first.json()
    assert write(customer, 'incident', 'incident-one', {**payload, 'title': 'Changed'}, key='repeat-safe').status_code == 409
    assert write(customer, 'incident', 'incident-one', payload).status_code == 409
    assert write(customer, 'incident', 'incident-one', {**payload, 'status': 'resolved'}, revision=1).status_code == 201
    evidence = customer.get('/api/v1/evidence').json()
    assert evidence['audit_valid'] is True
    assert len([r for r in evidence['versions'] if r['record_id'] == 'incident-one']) == 2


def test_references_and_payload_are_validated_atomically(customer):
    response = write(customer, 'call', 'bad', {'vessel_id': 'missing', 'eta': '2026-10-05T10:00:00Z', 'etd': '2026-10-05T15:00:00Z'})
    assert response.status_code == 422
    assert write(customer, 'port', 'bad', {'name': 'P', 'timezone': 'fake-zone'}).status_code == 422
    assert write(customer, 'port', 'bad', {'name': 'P', 'timezone': 'UTC', 'invented': True}).status_code == 422
    assert customer.get('/api/v1/workspace').json()['records'] == []


def test_port_coordinates_are_optional_but_validated(customer):
    recorded = write(customer, 'port', 'geo-port', {
        'name': 'Coordinate Port', 'timezone': 'Asia/Karachi',
        'latitude': 24.8441, 'longitude': 66.9762,
    })
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()['payload']['latitude'] == 24.8441
    assert recorded.json()['payload']['longitude'] == 66.9762
    assert write(customer, 'port', 'bad-port-lat', {
        'name': 'Bad latitude', 'timezone': 'UTC', 'latitude': 91, 'longitude': 66.9,
    }).status_code == 422
    assert write(customer, 'port', 'bad-port-lon', {
        'name': 'Bad longitude', 'timezone': 'UTC', 'latitude': 24.8, 'longitude': 181,
    }).status_code == 422


def test_berth_coordinates_are_optional_but_validated(customer):
    assert write(customer, 'port', 'p', {'name': 'P', 'timezone': 'UTC'}).status_code == 201
    recorded = write(customer, 'berth', 'geo-berth', {
        'name': 'Coordinate Quay', 'port_id': 'p',
        'latitude': 24.8441, 'longitude': 66.9762,
    })
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()['payload']['latitude'] == 24.8441
    assert recorded.json()['payload']['longitude'] == 66.9762
    assert write(customer, 'berth', 'bad-lat', {
        'name': 'Bad latitude', 'port_id': 'p', 'latitude': 91, 'longitude': 66.9,
    }).status_code == 422
    assert write(customer, 'berth', 'bad-lon', {
        'name': 'Bad longitude', 'port_id': 'p', 'latitude': 24.8, 'longitude': 181,
    }).status_code == 422


def test_two_clock_history_preserves_late_corrections(customer):
    original = write(customer, 'port', 'p', {'name': 'Original', 'timezone': 'UTC'}, valid_at='2026-01-01T00:00:00Z').json()
    corrected = write(customer, 'port', 'p', {'name': 'Corrected', 'timezone': 'UTC'}, revision=1, valid_at='2026-01-01T00:00:00Z')
    assert corrected.status_code == 201
    historical = customer.get('/api/v1/workspace', params={'known_at': original['known_at'], 'valid_at': '2026-02-01T00:00:00Z'}).json()
    assert historical['records'][0]['payload']['name'] == 'Original'
    current = customer.get('/api/v1/workspace', params={'valid_at': '2026-02-01T00:00:00Z'}).json()
    assert current['records'][0]['payload']['name'] == 'Corrected'
    assert write(customer, 'port', 'p', {'name': 'Future', 'timezone': 'UTC'}, revision=2, valid_at='2099-01-01T00:00:00Z').status_code == 201
    assert customer.get('/api/v1/workspace').json()['records'][0]['payload']['name'] == 'Corrected'


def test_invite_viewer_permissions_and_revoke(customer):
    token = invite(customer, 'viewer')
    viewer = activate(customer.app, token, 'viewer')
    assert viewer.get('/api/v1/workspace').status_code == 200
    assert write(viewer, 'port', 'denied', {'name': 'No', 'timezone': 'UTC'}).status_code == 403
    assert viewer.post('/api/v1/auth/invitations', headers=headers(viewer), json={'email': 'x@example.test', 'role': 'admin'}).status_code == 403
    assert viewer.post('/api/v1/auth/accept', headers={'Origin': ORIGIN}, json={
        'invitation_token': token, 'email': 'viewer@example.test', 'display_name': 'Again', 'password': PASSWORD}).status_code == 403
    user_id = viewer.get('/api/v1/auth/me').json()['user']['id']
    assert customer.post(f'/api/v1/team/{user_id}/revoke', headers=headers(customer)).status_code == 200
    assert viewer.get('/api/v1/workspace').status_code == 401


def test_logout_revokes_cookie_even_if_replayed(customer):
    old = customer.cookies.get('shorefront_session')
    assert customer.post('/api/v1/auth/logout', headers=headers(customer)).status_code == 200
    customer.cookies.set('shorefront_session', old)
    assert customer.get('/api/v1/auth/me').status_code == 401


def test_login_rate_limit(customer):
    for _ in range(5):
        response = customer.post('/api/v1/auth/login', headers={'Origin': ORIGIN}, json={'email': 'owner@example.test', 'password': 'incorrect'})
        assert response.status_code == 401
    assert customer.post('/api/v1/auth/login', headers={'Origin': ORIGIN}, json={'email': 'owner@example.test', 'password': 'incorrect'}).status_code == 429


def test_restart_preserves_facts_but_not_synthetic_records(tmp_path):
    path = tmp_path / 'durable.db'
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        bootstrap(client)
        setup_call(client)
        original = client.get('/api/v1/evidence').json()
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        response = client.post('/api/v1/auth/login', headers={'Origin': ORIGIN}, json={'email': 'owner@example.test', 'password': PASSWORD})
        assert response.status_code == 200
        assert client.get('/api/v1/evidence').json() == original
        assert len(client.get('/api/v1/workspace').json()['records']) == 4


def test_wrong_owner_restore_rejected(tmp_path):
    from shorefront_api.product_api import create_product_app
    path = tmp_path / 'owner.db'
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        bootstrap(client)
    with pytest.raises(RuntimeError, match='installation'):
        with TestClient(create_product_app(database_url=f'sqlite:///{path}', installation_id='other-customer', origin=ORIGIN, bootstrap_token=BOOTSTRAP)):
            pass


def test_tasks_have_real_assignment_and_completion(customer):
    setup_call(customer)
    token = invite(customer)
    operator = activate(customer.app, token)
    user_id = operator.get('/api/v1/auth/me').json()['user']['id']
    payload = {'title': 'Arrange replacement tug', 'call_id': 'call-one', 'assignee_id': user_id, 'due_at': '2026-10-05T09:00:00Z'}
    assert write(operator, 'task', 'task-one', payload).status_code == 201
    assert write(operator, 'task', 'task-one', {**payload, 'status': 'done'}, revision=1).status_code == 422
    assert write(operator, 'task', 'task-one', {**payload, 'status': 'done', 'completion_note': 'Replacement confirmed by dispatcher'}, revision=1).status_code == 201
    workspace = operator.get('/api/v1/workspace').json()
    assert workspace['attention'] == []
    graph = operator.get('/api/v1/graph').json()
    assert any(e['source'] == 'task:task-one' and e['target'] == 'call:call-one' for e in graph['edges'])


def test_handoff_requires_actual_named_recipient_acknowledgement(customer):
    setup_call(customer)
    recipient = activate(customer.app, invite(customer))
    recipient_id = recipient.get('/api/v1/auth/me').json()['user']['id']
    payload = {'title': 'Arrival brief', 'call_id': 'call-one', 'recipient_id': recipient_id,
               'due_at': '2026-10-05T09:00:00Z', 'note': 'Read arrival restrictions'}
    first = write(customer, 'handoff', 'h-one', payload)
    assert first.status_code == 201, first.text
    assert write(customer, 'handoff', 'h-forged', {**payload, 'status': 'acknowledged', 'proof': 'claimed receipt'}).status_code == 409
    sent = {**payload, 'status': 'sent'}
    assert write(customer, 'handoff', 'h-one', sent, revision=1).status_code == 201
    ack = {**sent, 'status': 'acknowledged', 'proof': 'I have read and understood the arrival restrictions'}
    assert write(customer, 'handoff', 'h-one', ack, revision=2).status_code == 403
    assert write(recipient, 'handoff', 'h-one', ack, revision=2).status_code == 201
    assert write(recipient, 'handoff', 'h-one', {**ack, 'note': 'rewritten'}, revision=3).status_code == 409
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_commitment_acceptance_is_recipient_bound(customer):
    setup_call(customer)
    recipient = activate(customer.app, invite(customer))
    identity = recipient.get('/api/v1/auth/me').json()['user']['id']
    payload = {'title': 'Supply tug', 'call_id': 'call-one', 'recipient_id': identity,
               'due_at': '2026-10-05T09:00:00Z'}
    assert write(customer, 'commitment', 'c-one', payload).status_code == 201
    assert write(customer, 'commitment', 'c-one', {**payload, 'status': 'accepted'}, revision=1).status_code == 403
    assert write(recipient, 'commitment', 'c-one', {**payload, 'status': 'accepted'}, revision=1).status_code == 201
    assert write(recipient, 'commitment', 'c-one', {**payload, 'status': 'fulfilled', 'proof': 'Dispatcher confirmation reference 20'}, revision=2).status_code == 201


def test_obligations_are_reviewed_not_legal_or_cash_claims(customer):
    setup_call(customer)
    me = customer.get('/api/v1/auth/me').json()['user']['id']
    payload = {'title': 'Submit arrival notice', 'call_id': 'call-one', 'assignee_id': me,
               'due_at': '2026-10-05T09:00:00Z', 'clause_reference': 'Customer SOP section 4', 'status': 'draft'}
    assert write(customer, 'obligation', 'o-one', payload).status_code == 201
    assert write(customer, 'obligation', 'o-one', {**payload, 'status': 'completed'}, revision=1).status_code == 422
    assert write(customer, 'obligation', 'o-one', {**payload, 'status': 'active', 'review_note': 'Checked against current customer SOP'}, revision=1).status_code == 201
    assert write(customer, 'obligation', 'o-one', {**payload, 'status': 'completed', 'review_note': 'Checked against current customer SOP', 'proof': 'Notice delivery receipt 34'}, revision=2).status_code == 201


def test_conflict_view_explains_overlapping_calls_without_invented_cost(customer):
    setup_call(customer)
    assert write(customer, 'call', 'second-call', {'vessel_id': 'vessel-one', 'berth_id': 'berth-one',
        'eta': '2026-10-05T12:00:00Z', 'etd': '2026-10-05T17:00:00Z'}).status_code == 201
    response = customer.get('/api/v1/conflicts')
    assert response.status_code == 200
    conflicts = response.json()
    assert any(c['kind'] == 'berth_overlap' and set(c['record_ids']) == {'call-one', 'second-call'} for c in conflicts)
    assert all('cash_saved' not in c for c in conflicts)


def test_expired_sessions_and_invitations_are_denied(customer):
    from sqlalchemy import update
    from shorefront_api.product_store import sessions, invitations
    token = invite(customer)
    with customer.app.state.product_store.transaction() as connection:
        connection.execute(update(invitations).values(expires_at='2000-01-01T00:00:00.000000+00:00'))
    assert customer.post('/api/v1/auth/accept', headers={'Origin': ORIGIN}, json={
        'invitation_token': token, 'email': 'operator@example.test', 'display_name': 'Expired', 'password': PASSWORD}).status_code == 403
    with customer.app.state.product_store.transaction() as connection:
        connection.execute(update(sessions).values(expires_at='2000-01-01T00:00:00.000000+00:00'))
    assert customer.get('/api/v1/workspace').status_code == 401


def test_audit_tampering_detected(customer):
    from sqlalchemy import update
    from shorefront_api.product_store import audit
    with customer.app.state.product_store.transaction() as connection:
        connection.execute(update(audit).values(payload='{}'))
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is False


def test_concurrent_writers_keep_one_revision(customer):
    from concurrent.futures import ThreadPoolExecutor
    cookie = customer.cookies.get('shorefront_session')
    csrf = customer.get('/api/v1/auth/me').json()['csrf_token']
    def send(index):
        client = TestClient(customer.app, base_url=ORIGIN)
        client.cookies.set('shorefront_session', cookie)
        return client.post('/api/v1/records/port', headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf, 'Idempotency-Key': f'concurrent-{index}'},
            json={'record_id': 'shared', 'expected_revision': 0, 'source': 'operator', 'payload': {'name': f'Port {index}', 'timezone': 'UTC'}}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(send, [1, 2]))
    assert sorted(statuses) == [201, 409]
    assert len(customer.get('/api/v1/workspace').json()['records']) == 1


def preview(customer):
    response = customer.post('/api/v1/decisions', headers=headers(customer), json={'call_id': 'call-one', 'question': 'Which recorded berth window should we use?'})
    assert response.status_code == 201, response.text
    return response.json()


def test_decision_preserves_inputs_and_supervisor_approval(customer):
    setup_call(customer)
    packet = preview(customer)
    assert packet['inputs'] and packet['trust']['confidence'] == 'uncalibrated'
    assert packet['options'][0]['label'] == 'Keep recorded plan'
    decision_id = packet['id']
    choice = {'option_id': packet['options'][0]['id'], 'reason': 'Reviewed the recorded schedule and constraints'}
    assert customer.post(f'/api/v1/decisions/{decision_id}/approve', headers=headers(customer), json=choice).status_code == 403
    supervisor = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    response = supervisor.post(f'/api/v1/decisions/{decision_id}/approve', headers=headers(supervisor), json=choice)
    assert response.status_code == 200, response.text
    assert response.json()['approved_by'] == supervisor.get('/api/v1/auth/me').json()['user']['id']
    again = supervisor.post(f'/api/v1/decisions/{decision_id}/approve', headers=headers(supervisor), json=choice)
    assert again.json() == response.json()
    changed = {**choice, 'reason': 'Different approval'}
    assert supervisor.post(f'/api/v1/decisions/{decision_id}/approve', headers=headers(supervisor), json=changed).status_code == 409
    assert customer.get(f'/api/v1/decisions/{decision_id}').json()['inputs'] == packet['inputs']
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_stale_decision_cannot_overwrite_new_facts(customer):
    setup_call(customer)
    packet = preview(customer)
    assert write(customer, 'port', 'port-one', {'name': 'Corrected Port', 'timezone': 'Asia/Karachi'}, revision=1).status_code == 201
    supervisor = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    response = supervisor.post(f"/api/v1/decisions/{packet['id']}/approve", headers=headers(supervisor), json={
        'option_id': packet['options'][0]['id'], 'reason': 'Review'})
    assert response.status_code == 409
    assert customer.get(f"/api/v1/decisions/{packet['id']}").json()['receipt'] is None


def test_bulk_import_rolls_back_all_rows_on_invalid_reference(customer):
    body = {'records': [
        {'kind': 'port', 'command': {'record_id': 'import-port', 'expected_revision': 0, 'source': 'Customer import', 'payload': {'name': 'Imported port', 'timezone': 'UTC'}}},
        {'kind': 'berth', 'command': {'record_id': 'bad-berth', 'expected_revision': 0, 'source': 'Customer import', 'payload': {'name': 'Bad', 'port_id': 'absent'}}}]}
    response = customer.post('/api/v1/imports', headers=headers(customer, 'import-1'), json=body)
    assert response.status_code == 422
    assert customer.get('/api/v1/workspace').json()['records'] == []
    body['records'][1]['command']['payload']['port_id'] = 'import-port'
    first = customer.post('/api/v1/imports', headers=headers(customer, 'import-1'), json=body)
    assert first.status_code == 201
    replay = customer.post('/api/v1/imports', headers=headers(customer, 'import-1'), json=body)
    assert replay.json() == first.json()
    body['records'].pop()
    assert customer.post('/api/v1/imports', headers=headers(customer, 'import-1'), json=body).status_code == 409


def test_password_change_rotates_all_sessions(customer):
    second = TestClient(customer.app, base_url=ORIGIN)
    assert second.post('/api/v1/auth/login', headers={'Origin': ORIGIN}, json={'email': 'owner@example.test', 'password': PASSWORD}).status_code == 200
    response = customer.post('/api/v1/auth/password', headers=headers(customer), json={'current_password': PASSWORD, 'new_password': 'another long test passphrase 43'})
    assert response.status_code == 200
    assert second.get('/api/v1/workspace').status_code == 401
    assert customer.get('/api/v1/workspace').status_code == 200


def test_corrupted_fact_does_not_pass_evidence_verification(customer):
    from sqlalchemy import update
    from shorefront_api.product_store import versions
    setup_call(customer)
    with customer.app.state.product_store.transaction() as connection:
        connection.execute(update(versions).where(versions.c.kind == 'port').values(payload='{"name":"altered","timezone":"UTC"}'))
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is False


def test_verify_schema_mode_never_creates_missing_tables(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOREFRONT_SCHEMA_MODE', 'verify')
    with pytest.raises(RuntimeError, match='schema'):
        with TestClient(build_app(tmp_path / 'unmigrated.db'), base_url=ORIGIN):
            pass


def test_expired_session_never_reaches_operational_socket(customer):
    from starlette.websockets import WebSocketDisconnect
    customer.cookies.clear()
    with pytest.raises(WebSocketDisconnect):
        with customer.websocket_connect('/ws/harbor'):
            pass


def test_observed_outcome_measures_error_without_claiming_cash(customer):
    setup_call(customer)
    assert write(customer, 'call', 'call-one', {'vessel_id':'vessel-one','berth_id':'berth-one',
        'eta':'2026-01-05T10:00:00Z','etd':'2026-01-05T15:00:00Z'}, revision=1).status_code == 201
    packet = preview(customer)
    supervisor = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    payload = {'decision_id': packet['id'], 'actual_arrival': '2026-01-05T10:30:00Z', 'actual_departure': '2026-01-05T16:00:00Z'}
    assert write(customer, 'outcome', 'outcome-one', payload).status_code == 422
    approved = supervisor.post(f"/api/v1/decisions/{packet['id']}/approve", headers=headers(supervisor), json={'option_id':'option-0','reason':'Review complete'})
    assert approved.status_code == 200
    assert write(customer, 'outcome', 'outcome-one', payload).status_code == 201
    result = customer.get('/api/v1/outcomes').json()
    assert result['sample_count'] == 1
    assert result['mean_absolute_arrival_error_minutes'] == 30
    assert result['observations'][0]['occupancy_error_minutes'] == 30
    assert result['confidence'] == 'descriptive_only'
    future = {**payload, 'actual_arrival':'2099-01-05T10:00:00Z','actual_departure':'2099-01-05T11:00:00Z'}
    assert write(customer, 'outcome', 'outcome-one', future, revision=1).status_code == 422


def test_operator_account_recovery_revokes_previous_sessions(customer):
    from shorefront_api import product_admin
    store = customer.app.state.product_store
    product_admin.reset_password(store, 'owner@example.test', 'replacement recovery passphrase 45', 'Owner identity checked offline')
    assert customer.get('/api/v1/workspace').status_code == 401
    assert customer.post('/api/v1/auth/login', headers={'Origin':ORIGIN}, json={'email':'owner@example.test','password':'replacement recovery passphrase 45'}).status_code == 200


def test_unicode_invalid_secrets_are_denied_not_server_errors(customer):
    bad = headers(customer)
    bad['X-CSRF-Token'] = 'wrong'
    assert customer.post('/api/v1/auth/bootstrap', headers={'Origin':ORIGIN}, json={
        'bootstrap_token':'not-a-secret-🔒','email':'x@example.test','display_name':'X','password':PASSWORD}).status_code == 403


def test_whitespace_password_is_not_silently_normalized(customer):
    password = '  a passphrase with meaningful spaces  '
    response = customer.post('/api/v1/auth/password', headers=headers(customer), json={'current_password':PASSWORD,'new_password':password})
    assert response.status_code == 200
    other = TestClient(customer.app, base_url=ORIGIN)
    assert other.post('/api/v1/auth/login', headers={'Origin':ORIGIN}, json={'email':'owner@example.test','password':password.strip()}).status_code == 401
    assert other.post('/api/v1/auth/login', headers={'Origin':ORIGIN}, json={'email':'owner@example.test','password':password}).status_code == 200


def test_decision_option_tampering_invalidates_export(customer):
    import json
    from sqlalchemy import update
    from shorefront_api.product_decisions import packets
    setup_call(customer)
    packet = preview(customer)
    packet['options'][0]['eligible'] = False
    with customer.app.state.product_store.transaction() as connection:
        connection.execute(update(packets).where(packets.c.id == packet['id']).values(payload=json.dumps(packet)))
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is False


def test_bootstrap_window_expires_without_startup_reset(tmp_path):
    from sqlalchemy import update
    from shorefront_api.product_store import installation
    path = tmp_path / 'setup-window.db'
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        with client.app.state.product_store.transaction() as connection:
            connection.execute(update(installation).values(bootstrap_expires_at='2000-01-01T00:00:00.000000+00:00'))
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        response = client.post('/api/v1/auth/bootstrap', headers={'Origin':ORIGIN}, json={
            'bootstrap_token':BOOTSTRAP,'email':'owner@example.test','display_name':'Owner','password':PASSWORD})
        assert response.status_code == 403
        from shorefront_api.product_admin import reopen_setup
        reopen_setup(client.app.state.product_store, 'Operator renewed initial setup after verification')
        bootstrap(client)


def test_initial_setup_deadline_is_persisted_for_twenty_four_hours(tmp_path):
    from sqlalchemy import select
    from shorefront_api.product_store import installation
    path = tmp_path / 'initial-deadline.db'
    before = datetime.now(timezone.utc)
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        with client.app.state.product_store.transaction() as connection:
            deadline = connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one()
        assert before + timedelta(hours=24) <= datetime.fromisoformat(deadline) <= datetime.now(timezone.utc) + timedelta(hours=24)
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        with client.app.state.product_store.transaction() as connection:
            assert connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one() == deadline


def test_reopen_setup_requires_reason_and_audits_renewal(tmp_path):
    import json
    from sqlalchemy import select, update
    from shorefront_api.product_admin import reopen_setup
    from shorefront_api.product_store import audit, installation
    with TestClient(build_app(tmp_path / 'renewal.db'), base_url=ORIGIN) as client:
        store = client.app.state.product_store
        with store.transaction() as connection:
            connection.execute(update(installation).values(bootstrap_expires_at='2000-01-01T00:00:00.000000+00:00'))
        with pytest.raises(ValueError, match='reason'):
            reopen_setup(store, '   ')
        with store.transaction() as connection:
            assert connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one() == '2000-01-01T00:00:00.000000+00:00'
            assert connection.execute(select(audit.c.sequence)).first() is None
        before = datetime.now(timezone.utc)
        reopen_setup(store, '  Setup operator verified access  ')
        with store.transaction() as connection:
            deadline = connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one()
            event = json.loads(connection.execute(select(audit.c.payload)).scalar_one())
        assert before + timedelta(hours=24) <= datetime.fromisoformat(deadline) <= datetime.now(timezone.utc) + timedelta(hours=24)
        assert event['actor_id'] == 'installation-operator'
        assert event['action'] == 'installation.setup_reopened'
        assert event['detail'] == {'reason': 'Setup operator verified access', 'bootstrap_expires_at': deadline}
        bootstrap(client)
        assert client.get('/api/v1/evidence').json()['audit_valid'] is True


def test_reopen_setup_refuses_existing_accounts_even_if_revoked(customer):
    from sqlalchemy import select, update
    from shorefront_api.product_admin import reopen_setup
    from shorefront_api.product_store import audit, installation, users
    store = customer.app.state.product_store
    with store.transaction() as connection:
        connection.execute(update(users).values(active=0))
        deadline = connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one()
        events = connection.execute(select(audit.c.payload)).scalars().all()
    with pytest.raises(ValueError, match='already initialized'):
        reopen_setup(store, 'No active accounts remain')
    with store.transaction() as connection:
        assert connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one() == deadline
        assert connection.execute(select(audit.c.payload)).scalars().all() == events


def test_legacy_setup_deadline_migration_does_not_renew_window(tmp_path):
    import sqlite3
    from sqlalchemy import select
    from shorefront_api.product_store import ProductStore, installation
    path = tmp_path / 'legacy-setup.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE sf_installation (id INTEGER PRIMARY KEY, owner VARCHAR(96) NOT NULL, version INTEGER NOT NULL)')
        connection.execute("INSERT INTO sf_installation VALUES (1, 'customer-a', 1)")
    store = ProductStore(f'sqlite:///{path}', 'customer-a')
    try:
        with pytest.raises(RuntimeError, match='schema'):
            store.initialize(migrate=False)
        store.initialize()
        with store.transaction() as connection:
            deadline = connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one()
        assert datetime.fromisoformat(deadline) < datetime.now(timezone.utc)
        store.initialize(migrate=False)
        with store.transaction() as connection:
            assert connection.execute(select(installation.c.bootstrap_expires_at)).scalar_one() == deadline
    finally:
        store.engine.dispose()
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        assert client.post('/api/v1/auth/bootstrap', headers={'Origin': ORIGIN}, json={
            'bootstrap_token': BOOTSTRAP, 'email': 'owner@example.test', 'display_name': 'Owner', 'password': PASSWORD}).status_code == 403


def test_standalone_store_initializes_complete_evidence_schema(tmp_path):
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-c',
        "from shorefront_api.product_store import ProductStore; "
        "import sys; store = ProductStore(sys.argv[1], 'customer-a'); store.initialize(); "
        "connection = store.engine.connect(); assert store.evidence(connection)['audit_valid']; "
        "connection.close(); store.engine.dispose()", f'sqlite:///{tmp_path / "standalone.db"}'],
        text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_admin_cli_reopens_setup_without_password_prompt(tmp_path):
    import os
    import subprocess
    import sys
    from sqlalchemy import update
    from shorefront_api.product_store import installation
    path = tmp_path / 'cli-setup.db'
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        with client.app.state.product_store.transaction() as connection:
            connection.execute(update(installation).values(bootstrap_expires_at='2000-01-01T00:00:00.000000+00:00'))
    result = subprocess.run([sys.executable, '-m', 'shorefront_api.product_admin', '--reopen-setup',
        '--reason', 'Operator verified initial setup'], input='', text=True, capture_output=True, timeout=30,
        env={**os.environ, 'DATABASE_URL': f'sqlite:///{path}', 'SHOREFRONT_INSTALLATION_ID': 'customer-a'})
    assert result.returncode == 0, result.stderr
    assert '24 hours' in result.stdout
    with TestClient(build_app(path), base_url=ORIGIN) as client:
        bootstrap(client)


@pytest.mark.parametrize('arguments', [
    ['--reopen-setup', '--email', 'owner@example.test', '--reason', 'Verified'],
    ['--reopen-setup'],
    ['--reason', 'Verified'],
])
def test_admin_cli_requires_one_action_and_reason(arguments):
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-m', 'shorefront_api.product_admin', *arguments],
        input='', text=True, capture_output=True, timeout=30)
    assert result.returncode == 2
    assert 'error:' in result.stderr

def test_cross_source_fact_disagreement_requires_explicit_resolution(customer):
    original = {'name': 'MV Resolve', 'imo': '1234567', 'length_m': 200}
    changed = {'name': 'MV Resolve', 'imo': '1234567', 'length_m': 212}
    assert write(customer, 'vessel', 'vessel-reconcile', original).status_code == 201

    operator = activate(customer.app, invite(customer))
    second = write(operator, 'vessel', 'vessel-reconcile', changed, revision=1)
    assert second.status_code == 201, second.text

    pending = customer.get('/api/v1/reconciliation/conflicts', params={'state': 'unresolved'})
    assert pending.status_code == 200, pending.text
    conflicts = pending.json()
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict['kind'] == 'vessel'
    assert conflict['record_id'] == 'vessel-reconcile'
    assert conflict['fields'] == ['length_m']
    assert conflict['state'] == 'unresolved'
    assert conflict['baseline']['revision'] == 1
    assert conflict['challenger']['revision'] == 2
    assert conflict['baseline']['actor_id'] != conflict['challenger']['actor_id']

    evidence_before = customer.get('/api/v1/evidence').json()
    assert evidence_before['audit_valid'] is True
    assert evidence_before['conflicts'][0]['state'] == 'unresolved'

    resolution = customer.post(
        f"/api/v1/reconciliation/conflicts/{conflict['id']}/resolve",
        headers=headers(customer, 'resolve-vessel-reconcile'),
        json={'accepted_revision': 1, 'note': 'Harbor master confirmed the registered vessel particulars.'},
    )
    assert resolution.status_code == 200, resolution.text
    resolved = resolution.json()
    assert resolved['state'] == 'resolved'
    assert resolved['accepted_revision'] == 1
    assert resolved['resolution_revision'] == 3

    current = next(
        record for record in customer.get('/api/v1/workspace').json()['records']
        if record['kind'] == 'vessel' and record['record_id'] == 'vessel-reconcile'
    )
    assert current['revision'] == 3
    assert current['payload'] == conflict['baseline']['payload']
    assert current['source'].startswith('reconciliation:')

    versions = [
        row for row in customer.get('/api/v1/history').json()
        if row['kind'] == 'vessel' and row['record_id'] == 'vessel-reconcile'
    ]
    assert [row['revision'] for row in versions] == [1, 2, 3]
    assert versions[1]['payload'] == conflict['challenger']['payload']
    assert versions[2]['payload'] == conflict['baseline']['payload']

    evidence_after = customer.get('/api/v1/evidence').json()
    assert evidence_after['audit_valid'] is True
    assert evidence_after['conflicts'][0]['state'] == 'resolved'
    assert evidence_after['conflicts'][0]['resolution_note'].startswith('Harbor master confirmed')


def test_same_actor_correction_does_not_create_source_conflict(customer):
    original = {'name': 'MV Same Actor', 'length_m': 180}
    corrected = {'name': 'MV Same Actor', 'length_m': 181}
    assert write(customer, 'vessel', 'vessel-same-actor', original).status_code == 201
    assert write(customer, 'vessel', 'vessel-same-actor', corrected, revision=1).status_code == 201
    conflicts = customer.get('/api/v1/reconciliation/conflicts', params={'state': 'unresolved'})
    assert conflicts.status_code == 200
    assert conflicts.json() == []


def test_conflict_ledger_tampering_breaks_server_evidence_verification(customer):
    from sqlalchemy import update
    from shorefront_api.product_store import fact_conflicts
    assert write(customer, 'vessel', 'tamper-conflict-vessel',
                 {'name':'Tamper Conflict Vessel','length_m':180}).status_code == 201
    operator = activate(customer.app, invite(customer))
    assert write(operator, 'vessel', 'tamper-conflict-vessel',
                 {'name':'Tamper Conflict Vessel','length_m':199}, revision=1).status_code == 201
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True
    with customer.app.state.product_store.transaction() as connection:
        connection.execute(update(fact_conflicts).values(fields='["name"]'))
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is False


def test_reconciliation_table_requires_explicit_migration(tmp_path):
    from sqlalchemy import inspect, text
    from shorefront_api.product_store import ProductStore, fact_conflicts
    url = f"sqlite:///{tmp_path / 'reconciliation-migration.db'}"
    store = ProductStore(url, 'customer-a')
    store.initialize(migrate=True)
    with store.engine.begin() as connection:
        connection.execute(text('DROP TABLE sf_fact_conflict'))
    with pytest.raises(RuntimeError, match='schema is missing'):
        store.initialize(migrate=False)
    store.initialize(migrate=True)
    assert fact_conflicts.name in inspect(store.engine).get_table_names()
    store.initialize(migrate=False)
    store.engine.dispose()
