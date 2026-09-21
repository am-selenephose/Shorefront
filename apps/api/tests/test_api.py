import hashlib
import json
import os

from fastapi.testclient import TestClient

VIEWER_TOKEN = "viewer-test-token"
OPERATOR_TOKEN = "operator-test-token"
SUPERVISOR_TOKEN = "supervisor-test-token"

os.environ["PORTFLOW_APPROVERS_JSON"] = json.dumps([
    {
        "token_sha256": hashlib.sha256(VIEWER_TOKEN.encode()).hexdigest(),
        "operator_id": "viewer-01",
        "display_name": "Read Only",
        "role": "viewer",
    },
    {
        "token_sha256": hashlib.sha256(OPERATOR_TOKEN.encode()).hexdigest(),
        "operator_id": "operator-17",
        "display_name": "Mina Torres",
        "role": "operator",
    },
    {
        "token_sha256": hashlib.sha256(SUPERVISOR_TOKEN.encode()).hexdigest(),
        "operator_id": "supervisor-02",
        "display_name": "Alex Chen",
        "role": "supervisor",
    },
])

from portflow_api.main import app


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}

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


def test_dependency_graph_endpoint():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.get("/api/v1/port-calls/pc-aurora/dependency-graph")
        assert response.status_code == 200
        data = response.json()
        assert data["port_call_id"] == "pc-aurora"
        assert len(data["nodes"]) == 7
        assert len(data["edges"]) == 6


def test_offline_replay_api_contract():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        client.post("/api/v1/connectivity", json={"mode": "offline_edge"})
        client.post(
            "/api/v1/incidents",
            json={
                "incident_type": "pilot_delay",
                "target_port_call_id": "pc-aurora",
                "impact_minutes": 25,
            },
        )
        pending = client.get("/api/v1/replay/pending").json()
        assert pending["pending"] >= 2

        connected = client.post("/api/v1/connectivity", json={"mode": "full"})
        assert connected.status_code == 200

        pending_after = client.get("/api/v1/replay/pending").json()
        assert pending_after["pending"] == 0

        receipts = client.get("/api/v1/replay/receipts").json()
        assert len(receipts) >= 2


def create_berth_recovery(client: TestClient) -> tuple[list[dict], str]:
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

    before = client.get("/api/v1/berth-conflicts").json()
    assert before

    payload = client.get("/api/v1/recovery/proposals?call_id=pc-nova").json()
    assert payload["auto_apply"] is False
    assert payload["count"] >= 1
    return before, payload["proposals"][0]["id"]


def test_auth_me_contract():
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get(
            "/api/v1/auth/me",
            headers=auth_headers("wrong-token"),
        ).status_code == 401

        viewer = client.get(
            "/api/v1/auth/me",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert viewer.status_code == 200
        assert viewer.json() == {
            "operator_id": "viewer-01",
            "display_name": "Read Only",
            "role": "viewer",
        }


def test_recovery_apply_requires_authenticated_approver():
    with TestClient(app) as client:
        before, proposal_id = create_berth_recovery(client)

        missing = client.post(f"/api/v1/recovery/proposals/{proposal_id}/apply")
        assert missing.status_code == 401

        invalid = client.post(
            f"/api/v1/recovery/proposals/{proposal_id}/apply",
            headers=auth_headers("invalid"),
        )
        assert invalid.status_code == 401

        viewer = client.post(
            f"/api/v1/recovery/proposals/{proposal_id}/apply",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert viewer.status_code == 403

        unchanged = client.get("/api/v1/berth-conflicts").json()
        assert unchanged == before


def test_operator_can_apply_and_receipt_binds_identity():
    with TestClient(app) as client:
        _, proposal_id = create_berth_recovery(client)

        applied = client.post(
            f"/api/v1/recovery/proposals/{proposal_id}/apply",
            headers=auth_headers(OPERATOR_TOKEN),
        )
        assert applied.status_code == 200
        receipt = applied.json()
        assert receipt["approved_by"] == "operator-17"
        assert receipt["approved_role"] == "operator"
        assert receipt["approved_display_name"] == "Mina Torres"

        after = client.get("/api/v1/berth-conflicts").json()
        assert after == []

        assert client.get("/api/v1/recovery/receipts").status_code == 401
        receipts = client.get(
            "/api/v1/recovery/receipts",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert receipts.status_code == 200
        rows = receipts.json()
        assert len(rows) == 1
        assert rows[0]["proposal_id"] == proposal_id
        assert rows[0]["approved_by"] == "operator-17"
        assert rows[0]["approved_role"] == "operator"


def test_supervisor_can_apply_recovery():
    with TestClient(app) as client:
        _, proposal_id = create_berth_recovery(client)

        applied = client.post(
            f"/api/v1/recovery/proposals/{proposal_id}/apply",
            headers=auth_headers(SUPERVISOR_TOKEN),
        )
        assert applied.status_code == 200
        receipt = applied.json()
        assert receipt["approved_by"] == "supervisor-02"
        assert receipt["approved_role"] == "supervisor"
        assert receipt["approved_display_name"] == "Alex Chen"
