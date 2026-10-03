"""Demonstration mutation controls require explicit runtime opt-in."""
import hashlib
import json

from fastapi.testclient import TestClient

from shorefront_api.main import app


def test_runtime_defaults_to_protected_controls(monkeypatch):
    monkeypatch.delenv('SHOREFRONT_DEMO_CONTROLS', raising=False)
    with TestClient(app) as client:
        response = client.get('/api/v1/runtime/capabilities')
        assert response.status_code == 200
        assert response.json()['demo_controls_enabled'] is False


def test_protected_runtime_preserves_state_when_demo_commands_are_requested(monkeypatch):
    monkeypatch.setenv('SHOREFRONT_DEMO_CONTROLS', '0')
    with TestClient(app) as client:
        before = client.get('/api/v1/harbor').json()['port_calls']
        for path, payload in [
            ('/api/v1/demo/reset', None),
            ('/api/v1/scenarios/tug-loss/run', None),
            ('/api/v1/connectivity', {'mode': 'offline_edge'}),
            ('/api/v1/replay', None),
        ]:
            assert client.post(path, json=payload).status_code == 403
        assert client.get('/api/v1/harbor').json()['port_calls'] == before
        # The isolated read-only story remains available.
        assert client.get('/api/v1/demo/story').status_code == 200


def test_protected_incident_commands_require_an_operator(monkeypatch):
    token = 'boundary-test-only'
    monkeypatch.setenv('SHOREFRONT_DEMO_CONTROLS', '0')
    monkeypatch.setenv('SHOREFRONT_APPROVERS_JSON', json.dumps([{
        'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
        'operator_id': 'boundary-test', 'display_name': 'Test operator', 'role': 'operator',
    }]))
    with TestClient(app) as client:
        body = {'incident_type': 'pilot_delay', 'target_port_call_id': 'pc-aurora', 'impact_minutes': 5}
        assert client.post('/api/v1/incidents', json=body).status_code == 401
        headers = {'Authorization': f'Bearer {token}'}
        created = client.post('/api/v1/incidents', json=body, headers=headers)
        assert created.status_code == 200
        incident_id = created.json()['id']
        assert client.patch(f'/api/v1/incidents/{incident_id}/resolve').status_code == 401
        assert client.patch(f'/api/v1/incidents/{incident_id}/resolve', headers=headers).status_code == 200
