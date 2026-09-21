from fastapi.testclient import TestClient
from portflow_api.main import app

def test_healthz():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True

def test_harbor_overview_contract():
    with TestClient(app) as client:
        data = client.get("/api/v1/harbor").json()
    assert data["port_name"] == "PortFlow Demo Harbor"
    assert len(data["vessels"]) >= 5
    assert len(data["berths"]) >= 5
    assert len(data["port_calls"]) >= 3
    assert "synthetic" in data["data_disclaimer"].lower()

def test_connectivity_degrades_without_losing_state():
    with TestClient(app) as client:
        before = client.get("/api/v1/harbor").json()
        changed = client.post("/api/v1/connectivity", json={"mode": "critical"}).json()
        after = client.get("/api/v1/harbor").json()
    assert changed["mode"] == "critical"
    assert changed["bandwidth_kbps"] == 10
    assert [v["id"] for v in before["vessels"]] == [v["id"] for v in after["vessels"]]


def test_risk_endpoint_is_explainable():
    with TestClient(app) as client:
        data = client.get("/api/v1/port-calls/pc-aurora/risk").json()
    assert data["found"] is True
    assert data["call_id"] == "pc-aurora"
    assert data["risk"] in {"low", "medium", "high", "critical"}
    assert isinstance(data["score"], int)
    assert isinstance(data["reasons"], list)


def test_conflict_endpoint_contract():
    with TestClient(app) as client:
        data = client.get("/api/v1/berth-conflicts").json()
    assert isinstance(data, list)


def test_incident_endpoint_propagates_and_persists():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        incident = client.post(
            "/api/v1/incidents",
            json={
                "incident_type": "berth_overrun",
                "target_port_call_id": "pc-glory",
                "impact_minutes": 90,
            },
        )
        assert incident.status_code == 200
        body = incident.json()
        assert body["incident_type"] == "berth_overrun"
        assert body["target_berth_id"] == "b-07"

        conflicts = client.get("/api/v1/berth-conflicts").json()
        assert any(c["berth_id"] == "b-07" for c in conflicts)

        ledger = client.get("/api/v1/events?limit=20").json()
        assert any(e["incident_id"] == body["id"] for e in ledger)

        persisted = client.get("/api/v1/incidents?limit=20").json()
        assert any(i["id"] == body["id"] for i in persisted)
