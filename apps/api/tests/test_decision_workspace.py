"""Read-only decision views must never mutate operational records."""
from fastapi.testclient import TestClient

from shorefront_api.main import app, store


def operational_records(client):
    harbor = client.get('/api/v1/harbor').json()
    return {
        'calls': harbor['port_calls'],
        'incidents': harbor['incidents'],
        'resources': harbor['service_resources'],
        'events': client.get('/api/v1/events').json(),
        'receipts': [r.model_dump(mode='json') for r in store.list_recovery_receipts()],
        'evidence': [e.model_dump(mode='json') for e in store.list_recovery_proposal_evidence()],
    }


def test_comparison_returns_projected_timelines_without_writing():
    with TestClient(app) as client:
        client.post('/api/v1/scenarios/tug-loss/run')
        before = operational_records(client)
        response = client.get('/api/v1/recovery/comparison')
        assert response.status_code == 200
        body = response.json()
        assert body['read_only'] is True
        assert body['options']
        for option in body['options']:
            proposal, projected = option['proposal'], option['harbor']
            assert sum(c['delay_minutes'] for c in projected['port_calls']) == proposal['projected_total_delay_minutes']
            assert sum(s['state'] == 'blocked' for s in projected['service_steps']) == proposal['projected_blocked_services']
            assert projected['berths']
        assert operational_records(client) == before


def test_guided_story_is_isolated_and_explicit_about_simulated_approval():
    with TestClient(app) as client:
        before = operational_records(client)
        response = client.get('/api/v1/demo/story')
        assert response.status_code == 200
        body = response.json()
        assert body['synthetic'] is True
        assert body['writes_operational_state'] is False
        assert body['comparison']['options']
        assert body['disrupted']['metrics']['blocked_services'] > body['baseline']['metrics']['blocked_services']
        assert body['receipt']['approved_by'] == 'guided-demo-simulation'
        assert body['receipt_is_simulated'] is True
        assert body['recovered']['metrics']['blocked_services'] < body['disrupted']['metrics']['blocked_services']
        assert body['dependency_graph']['nodes']
        assert client.get('/api/v1/demo/story').status_code == 200
        assert operational_records(client) == before
