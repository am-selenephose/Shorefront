from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from shorefront_api.product_store import source_standard_profiles, standard_events
from test_product import ORIGIN, bootstrap, build_app, headers


PROFILE = 'dcsa-port-call-2.0.0'
CALL_ID = '3910eb91-8791-4699-8029-8bba8cedb6f5'
ARRIVAL_EVENT = '11111111-1111-4111-8111-111111111111'
DEPARTURE_EVENT = '22222222-2222-4222-8222-222222222222'
ACTUAL_ARRIVAL = '33333333-3333-4333-8333-333333333333'
ACTUAL_DEPARTURE = '44444444-4444-4444-8444-444444444444'


@pytest.fixture
def client(tmp_path):
    app = build_app(tmp_path / 'standards.db')
    with TestClient(app, base_url=ORIGIN) as test_client:
        bootstrap(test_client)
        yield test_client


def source(client, *, profiles=None, kinds=None):
    response = client.post('/api/v1/connections/sources', headers=headers(client), json={
        'id': 'dcsa-feed',
        'name': 'DCSA Port Call publisher',
        'allowed_kinds': kinds or ['vessel', 'call'],
        'standard_profiles': profiles if profiles is not None else [PROFILE],
        'expires_in_hours': 24,
    })
    assert response.status_code == 201, response.text
    return response.json()['token']


def event(event_id, updated_at, event_type, classifier, service_time, *, service='BERTH'):
    return {
        'eventID': event_id,
        'eventUpdatedDateTime': updated_at,
        'isFYI': False,
        'portCall': {
            'portCallID': CALL_ID,
            'portVisitReference': 'NLAMS1234589',
            'UNLocationCode': 'NLAMS',
            'isOmitted': False,
        },
        'portCallService': {
            'portCallServiceID': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
            'portCallServiceTypeCode': service,
            'portCallServiceEventTypeCode': event_type,
            'portCallPhaseTypeCode': 'ALGS',
            'facilityTypeCode': 'BRTH',
            'isCanceled': False,
            'isDeclined': False,
        },
        'vessel': {
            'vesselIMONumber': '9321483',
            'vesselName': 'King of the Seas',
            'vesselSizeUnit': 'MTR',
            'lengthOverall': 245.45,
            'draftUnit': 'MTR',
            'draft': 12.5,
        },
        'timestamp': {
            'classifierCode': classifier,
            'serviceDateTime': service_time,
        },
    }


def post_events(client, token, events, key='dcsa-post-1'):
    return client.post(
        f'/api/v1/integrations/dcsa-feed/standards/{PROFILE}/events',
        headers={'Authorization': f'Bearer {token}', 'Idempotency-Key': key},
        json={'events': events},
    )


def workspace(client):
    return client.get('/api/v1/workspace').json()['records']


def test_profile_must_be_explicitly_granted(client):
    token = source(client, profiles=[])
    response = post_events(client, token, [
        event(ARRIVAL_EVENT, '2026-10-06T10:00:00Z', 'ARRI', 'EST', '2026-10-07T10:00:00Z')
    ])
    assert response.status_code == 403
    assert client.get('/api/v1/connections/standard-events', headers=headers(client)).json() == []


def test_partial_dcsa_evidence_is_held_then_materializes_native_call(client):
    token = source(client)
    arrival = post_events(client, token, [
        event(ARRIVAL_EVENT, '2026-10-06T10:00:00Z', 'ARRI', 'EST', '2026-10-07T10:00:00Z')
    ])
    assert arrival.status_code == 202, arrival.text
    assert arrival.json()['accepted_events'] == 1
    assert arrival.json()['materialized_records'] == []
    assert any('waiting for both berth arrival and departure' in item['message'].lower()
               for item in arrival.json()['feedbackElements'])
    assert not any(record['kind'] == 'call' for record in workspace(client))

    departure = post_events(client, token, [
        event(DEPARTURE_EVENT, '2026-10-06T10:01:00Z', 'DEPA', 'EST', '2026-10-07T15:00:00Z')
    ], key='dcsa-post-2')
    assert departure.status_code == 202, departure.text
    materialized = {(row['kind'], row['record_id']) for row in departure.json()['materialized_records']}
    assert ('vessel', 'imo_9321483') in materialized
    assert ('call', f'dcsa_{CALL_ID}') in materialized

    records = workspace(client)
    vessel = next(record for record in records if record['kind'] == 'vessel')
    call = next(record for record in records if record['kind'] == 'call')
    assert vessel['payload']['name'] == 'King of the Seas'
    assert vessel['payload']['imo'] == '9321483'
    assert vessel['payload']['length_m'] == 245.45
    assert vessel['payload']['draft_m'] == 12.5
    assert call['payload'] == {
        'vessel_id': 'imo_9321483',
        'berth_id': None,
        'eta': '2026-10-07T10:00:00Z',
        'etd': '2026-10-07T15:00:00Z',
        'status': 'planned',
    }
    assert call['source'] == f'standard:{PROFILE}:dcsa-feed'

    ledger = client.get('/api/v1/connections/standard-events', headers=headers(client)).json()
    assert len(ledger) == 2
    assert {item['state'] for item in ledger} <= {'held', 'materialized'}
    assert all(item['profile_id'] == PROFILE for item in ledger)


def test_actual_events_advance_status_without_rewriting_planning_times(client):
    token = source(client)
    planning = [
        event(ARRIVAL_EVENT, '2026-10-06T10:00:00Z', 'ARRI', 'PLN', '2026-10-07T10:00:00Z'),
        event(DEPARTURE_EVENT, '2026-10-06T10:01:00Z', 'DEPA', 'PLN', '2026-10-07T15:00:00Z'),
    ]
    assert post_events(client, token, planning).status_code == 202

    arrived = post_events(client, token, [
        event(ACTUAL_ARRIVAL, '2026-10-07T10:12:00Z', 'ARRI', 'ACT', '2026-10-07T10:12:00Z')
    ], key='actual-arrival')
    assert arrived.status_code == 202
    call = next(record for record in workspace(client) if record['kind'] == 'call')
    assert call['payload']['status'] == 'berthed'
    assert call['payload']['eta'] == '2026-10-07T10:00:00Z'
    assert call['payload']['etd'] == '2026-10-07T15:00:00Z'

    departed = post_events(client, token, [
        event(ACTUAL_DEPARTURE, '2026-10-07T15:20:00Z', 'DEPA', 'ACT', '2026-10-07T15:20:00Z')
    ], key='actual-departure')
    assert departed.status_code == 202
    call = next(record for record in workspace(client) if record['kind'] == 'call')
    assert call['payload']['status'] == 'departed'
    assert call['payload']['eta'] == '2026-10-07T10:00:00Z'
    assert call['payload']['etd'] == '2026-10-07T15:00:00Z'


def test_event_replay_and_newer_revision_are_versioned(client):
    token = source(client)
    first = event(ARRIVAL_EVENT, '2026-10-06T10:00:00Z', 'ARRI', 'EST', '2026-10-07T10:00:00Z')
    assert post_events(client, token, [first]).status_code == 202
    replay = post_events(client, token, [first], key='replay-different-request-key')
    assert replay.status_code == 202

    changed = deepcopy(first)
    changed['eventUpdatedDateTime'] = '2026-10-06T10:05:00Z'
    changed['timestamp']['serviceDateTime'] = '2026-10-07T10:30:00Z'
    revised = post_events(client, token, [changed], key='newer-revision')
    assert revised.status_code == 202

    with client.app.state.product_store.transaction() as connection:
        rows = connection.execute(select(standard_events).where(
            standard_events.c.source_id == 'dcsa-feed',
            standard_events.c.event_id == ARRIVAL_EVENT,
        ).order_by(standard_events.c.revision)).mappings().all()
    assert [row['revision'] for row in rows] == [1, 2]
    assert rows[0]['digest'] != rows[1]['digest']


def test_conflicting_non_newer_event_update_fails_closed(client):
    token = source(client)
    first = event(ARRIVAL_EVENT, '2026-10-06T10:00:00Z', 'ARRI', 'EST', '2026-10-07T10:00:00Z')
    assert post_events(client, token, [first]).status_code == 202

    conflict = deepcopy(first)
    conflict['timestamp']['serviceDateTime'] = '2026-10-07T12:00:00Z'
    response = post_events(client, token, [conflict], key='conflict')
    assert response.status_code == 202
    assert response.json()['accepted_events'] == 0
    assert any(item['severity'] == 'ERROR' for item in response.json()['feedbackElements'])
    with client.app.state.product_store.transaction() as connection:
        assert connection.execute(select(standard_events).where(
            standard_events.c.event_id == ARRIVAL_EVENT)).mappings().all().__len__() == 1


def test_unsupported_service_is_preserved_but_not_misclassified(client):
    token = source(client)
    pilotage = event(
        '55555555-5555-4555-8555-555555555555',
        '2026-10-06T11:00:00Z', 'STRT', 'EST', '2026-10-07T09:30:00Z',
        service='PILOTAGE',
    )
    response = post_events(client, token, [pilotage])
    assert response.status_code == 202
    assert response.json()['accepted_events'] == 1
    assert response.json()['materialized_records'] == []
    assert any('retained' in item['message'].lower() for item in response.json()['feedbackElements'])
    assert not workspace(client)


def test_standard_profile_and_event_registry_are_admin_only(client):
    profiles = client.get('/api/v1/connections/standards', headers=headers(client))
    assert profiles.status_code == 200
    profile = next(item for item in profiles.json() if item['id'] == PROFILE)
    assert profile['standard'] == 'DCSA Port Call'
    assert profile['version'] == '2.0.0'
    assert profile['conformance'] == 'subset-not-certified'

    token = source(client)
    assert post_events(client, token, [
        event(ARRIVAL_EVENT, '2026-10-06T10:00:00Z', 'ARRI', 'EST', '2026-10-07T10:00:00Z')
    ]).status_code == 202
    rows = client.get('/api/v1/connections/standard-events', headers=headers(client)).json()
    assert rows[0]['event_id'] == ARRIVAL_EVENT
    assert 'payload' not in rows[0]


def test_standard_tables_require_explicit_additive_migration(tmp_path):
    app = build_app(tmp_path / 'pre-standard.db')
    with TestClient(app, base_url=ORIGIN) as test_client:
        bootstrap(test_client)
        token = source(test_client)
        assert token
    store = app.state.product_store
    with store.engine.begin() as connection:
        standard_events.drop(connection)
        source_standard_profiles.drop(connection)
    with pytest.raises(RuntimeError, match='schema is missing'):
        store.initialize(migrate=False)
    store.initialize(migrate=True)
    store.initialize(migrate=False)
    with store.transaction() as connection:
        assert connection.execute(select(standard_events)).mappings().all() == []
        assert connection.execute(select(source_standard_profiles)).mappings().all() == []
    store.engine.dispose()
