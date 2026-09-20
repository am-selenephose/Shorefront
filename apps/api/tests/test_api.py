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
