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

from portflow_api.adapters import configured_live_adapters
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
        assert len(data["nodes"]) == 11
        assert len(data["edges"]) == 16

        nodes = {node["kind"]: node for node in data["nodes"]}
        assert set(nodes) == {
            "pilot",
            "tug",
            "berth",
            "crane",
            "cargo",
            "bunker",
            "stores",
            "documents",
            "customs",
            "gate",
            "departure",
        }
        assert set(nodes["customs"]["dependency_step_ids"]) == {
            "svc-pc-aurora-cargo",
            "svc-pc-aurora-documents",
        }
        assert set(nodes["departure"]["dependency_step_ids"]) == {
            "svc-pc-aurora-cargo",
            "svc-pc-aurora-bunker",
            "svc-pc-aurora-stores",
            "svc-pc-aurora-customs",
            "svc-pc-aurora-gate",
        }


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


def test_scenario_catalog_and_deterministic_berth_fixture():
    with TestClient(app) as client:
        catalog = client.get("/api/v1/scenarios")
        assert catalog.status_code == 200
        ids = {row["id"] for row in catalog.json()}
        assert {
            "berth-crunch",
            "tug-loss",
            "bunker-loss",
            "edge-pilot-delay",
            "wind-hold",
        } <= ids

        first = client.post("/api/v1/scenarios/berth-crunch/run")
        assert first.status_code == 200
        one = first.json()
        assert one["scenario"]["id"] == "berth-crunch"
        assert one["harbor"]["metrics"]["berth_conflicts"] == 1
        nova_one = next(call for call in one["harbor"]["port_calls"] if call["id"] == "pc-nova")
        assert nova_one["berth_id"] == "b-07"

        second = client.post("/api/v1/scenarios/berth-crunch/run")
        assert second.status_code == 200
        two = second.json()
        assert two["harbor"]["metrics"]["berth_conflicts"] == one["harbor"]["metrics"]["berth_conflicts"]
        nova_two = next(call for call in two["harbor"]["port_calls"] if call["id"] == "pc-nova")
        assert nova_two["berth_id"] == nova_one["berth_id"]
        assert len(two["recovery_proposals"]) == len(one["recovery_proposals"])


def test_scenario_fixture_offline_spools_local_events():
    with TestClient(app) as client:
        payload = client.post("/api/v1/scenarios/edge-pilot-delay/run")
        assert payload.status_code == 200
        data = payload.json()
        assert data["harbor"]["connectivity"]["mode"] == "offline_edge"
        assert data["harbor"]["connectivity"]["queued_events"] >= 1
        pending = client.get("/api/v1/replay/pending").json()
        assert pending["pending"] == data["harbor"]["connectivity"]["queued_events"]


def test_unknown_scenario_returns_404():
    with TestClient(app) as client:
        response = client.post("/api/v1/scenarios/not-real/run")
        assert response.status_code == 404


def test_adapter_catalog_exposes_provenance_and_stale_fixture():
    with TestClient(app) as client:
        response = client.get("/api/v1/adapters")
        assert response.status_code == 200
        rows = response.json()
        by_id = {row["adapter_id"]: row for row in rows}

        assert {"recorded-ais", "recorded-weather", "recorded-berth-plan", "stale-weather-fixture"} <= set(by_id)
        assert by_id["recorded-ais"]["provenance"]["mode"] == "recorded"
        assert by_id["recorded-ais"]["provenance"]["health"] == "healthy"
        assert by_id["stale-weather-fixture"]["provenance"]["stale"] is True
        assert by_id["stale-weather-fixture"]["provenance"]["health"] == "stale"


def test_adapter_ingest_requires_operator_and_updates_harbor_source():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        anonymous = client.post("/api/v1/adapters/recorded-ais/ingest")
        assert anonymous.status_code == 401

        viewer = client.post(
            "/api/v1/adapters/recorded-ais/ingest",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert viewer.status_code == 403

        operator = client.post(
            "/api/v1/adapters/recorded-ais/ingest",
            headers=auth_headers(OPERATOR_TOKEN),
        )
        assert operator.status_code == 200
        payload = operator.json()
        assert payload["applied_records"] == 2
        assert payload["adapter"]["mode"] == "recorded"
        assert payload["ingested_by"]["operator_id"] == "operator-17"

        harbor = client.get("/api/v1/harbor").json()
        aurora = next(vessel for vessel in harbor["vessels"] if vessel["id"] == "v-aurora")
        assert aurora["source_id"] == "recorded-ais"
        ais_source = next(source for source in harbor["data_sources"] if source["source_id"] == "recorded-ais")
        assert ais_source["source_id"] == "recorded-ais"
        assert "recorded fixture" in harbor["data_disclaimer"].lower()

        ledger = client.get("/api/v1/events?limit=20").json()
        adapter_event = next(event for event in ledger if event["category"] == "data_adapter")
        assert adapter_event["actor_id"] == "operator-17"
        assert adapter_event["actor_role"] == "operator"
        assert adapter_event["source_id"] == "recorded-ais"


def test_stale_adapter_ingest_returns_409():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.post(
            "/api/v1/adapters/stale-weather-fixture/ingest",
            headers=auth_headers(SUPERVISOR_TOKEN),
        )
        assert response.status_code == 409
        assert "stale" in response.json()["detail"].lower()


def test_bunker_loss_scenario_blocks_departure_and_returns_recovery_options():
    with TestClient(app) as client:
        response = client.post("/api/v1/scenarios/bunker-loss/run")
        assert response.status_code == 200
        payload = response.json()

        harbor = payload["harbor"]
        incident = harbor["incidents"][0]
        assert incident["incident_type"] == "bunker_unavailable"
        assert incident["target_resource_id"] == "bunker-barge-4"

        graph = client.get(
            "/api/v1/port-calls/pc-aurora/dependency-graph"
        ).json()
        nodes = {node["kind"]: node for node in graph["nodes"]}
        assert nodes["bunker"]["state"] == "blocked"
        assert nodes["departure"]["state"] == "blocked"

        bunker_proposals = [
            proposal for proposal in payload["recovery_proposals"]
            if any(
                action.get("service_kind") == "bunker"
                for action in proposal["actions"]
            )
        ]
        assert len(bunker_proposals) >= 2
        assert bunker_proposals[0]["projected_blocked_services"] == 0
        assert bunker_proposals[0]["disruption_score"] < bunker_proposals[1]["disruption_score"]


def test_live_adapter_preview_reuses_last_good_across_api_requests(monkeypatch):
    from datetime import datetime, timezone

    base = datetime.now(timezone.utc).replace(microsecond=0)
    monkeypatch.setenv("PORTFLOW_AIS_URL", "https://example.invalid/ais")
    monkeypatch.setenv("PORTFLOW_AIS_PROVIDER", "Persistent API AIS")

    adapter = configured_live_adapters()["live-ais"]
    calls = {"count": 0}

    def loader(url, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "observed_at": base.isoformat(),
                "records": [{
                    "vessel_id": "v-aurora",
                    "lat": 51.982,
                    "lon": 3.995,
                    "speed_knots": 10.9,
                    "heading_deg": 94.0,
                }],
            }
        raise TimeoutError("fixture outage")

    adapter.loader = loader

    with TestClient(app) as client:
        first = client.get("/api/v1/adapters/live-ais/preview")
        second = client.get("/api/v1/adapters/live-ais/preview")

    assert first.status_code == 200
    assert first.json()["provenance"]["health"] == "healthy"
    assert first.json()["provenance"]["last_success_at"] is not None

    assert second.status_code == 200
    assert second.json()["provenance"]["health"] == "degraded"
    assert second.json()["provenance"]["using_cached_records"] is True
    assert second.json()["provenance"]["consecutive_errors"] == 1
    assert second.json()["records"] == first.json()["records"]
