from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from uuid import uuid4

from fastapi.testclient import TestClient

VIEWER_TOKEN = "viewer-test-token"
OPERATOR_TOKEN = "operator-test-token"
SUPERVISOR_TOKEN = "supervisor-test-token"
INTEGRATION_TOKEN = "vessel-runtime-test-token"

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

os.environ["PORTFLOW_INTEGRATIONS_JSON"] = json.dumps([
    {
        "token_sha256": hashlib.sha256(INTEGRATION_TOKEN.encode()).hexdigest(),
        "integration_id": "vessel-runtime-aurora",
        "display_name": "Aurora Runtime",
        "vessel_ids": ["v-aurora"],
    }
])

from portflow_api.adapters import configured_live_adapters
import portflow_api.main as main_module
from portflow_api.main import app
from portflow_api.models import VesselRuntimeEvent, VesselRuntimeEventRecord


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
        third = client.get("/api/v1/adapters/live-ais/preview")

    assert first.status_code == 200
    assert first.json()["provenance"]["health"] == "healthy"
    assert first.json()["provenance"]["last_success_at"] is not None

    assert second.status_code == 200
    assert second.json()["provenance"]["health"] == "degraded"
    assert second.json()["provenance"]["using_cached_records"] is True
    assert second.json()["provenance"]["consecutive_errors"] == 1
    assert second.json()["provenance"]["next_retry_at"] is not None
    assert second.json()["provenance"]["retry_delay_seconds"] > 0
    assert second.json()["records"] == first.json()["records"]

    assert third.status_code == 200
    assert third.json()["provenance"]["consecutive_errors"] == 1
    assert third.json()["provenance"]["next_retry_at"] == second.json()["provenance"]["next_retry_at"]
    assert "Retry backoff active" in third.json()["provenance"]["detail"]
    assert calls["count"] == 2


def test_dual_resource_scenario_exposes_compound_recovery_contract():
    with TestClient(app) as client:
        catalog = client.get("/api/v1/scenarios")
        assert catalog.status_code == 200
        assert "dual-resource-loss" in {row["id"] for row in catalog.json()}

        response = client.post("/api/v1/scenarios/dual-resource-loss/run")
        assert response.status_code == 200
        payload = response.json()

        incidents = [
            incident
            for incident in payload["harbor"]["incidents"]
            if incident["status"] == "active"
            and incident["incident_type"] in {"tug_unavailable", "bunker_unavailable"}
        ]
        assert {incident["incident_type"] for incident in incidents} == {
            "tug_unavailable",
            "bunker_unavailable",
        }

        compound = [
            proposal
            for proposal in payload["recovery_proposals"]
            if len(proposal.get("incident_ids", [])) == 2
            and {
                action.get("service_kind")
                for action in proposal["actions"]
                if action.get("service_kind")
            } >= {"tug", "bunker"}
        ]
        assert compound

        best = min(compound, key=lambda proposal: proposal["disruption_score"])
        assert best["title"] == "Compound recovery: Tug 22 + Bunker Barge 9"
        assert set(best["incident_ids"]) == {incident["id"] for incident in incidents}
        assert best["projected_total_delay_minutes"] == 124
        assert best["projected_blocked_services"] == 0
        assert best["disruption_score"] == 149


def test_service_duration_calibration_api_enforces_authority_and_provenance():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        initial = client.get("/api/v1/service-duration-calibrations")
        assert initial.status_code == 200
        initial_payload = initial.json()
        assert initial_payload["count"] == 11
        initial_bunker = next(
            row for row in initial_payload["calibrations"]
            if row["service_kind"] == "bunker"
        )
        assert initial_bunker["duration_minutes"] == 60
        assert initial_bunker["mode"] == "synthetic"

        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = {
            "service_kind": "bunker",
            "duration_minutes": 75,
            "source_id": "recorded-bunker-calibration-api",
            "mode": "recorded",
            "provider": "Terminal service history replay",
            "observed_at": now.isoformat(),
            "stale_after_seconds": 86_400,
            "detail": "Recorded median bunker-service duration.",
        }

        assert client.post(
            "/api/v1/service-duration-calibrations",
            json=payload,
        ).status_code == 401
        assert client.post(
            "/api/v1/service-duration-calibrations",
            json=payload,
            headers=auth_headers(VIEWER_TOKEN),
        ).status_code == 403

        updated = client.post(
            "/api/v1/service-duration-calibrations",
            json=payload,
            headers=auth_headers(OPERATOR_TOKEN),
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["calibration"]["duration_minutes"] == 75
        assert body["calibration"]["mode"] == "recorded"
        assert body["provenance"]["domain"] == "service_calibration"
        assert body["updated_by"]["operator_id"] == "operator-17"

        harbor = client.get("/api/v1/harbor").json()
        calibrated = next(
            row for row in harbor["service_duration_calibrations"]
            if row["service_kind"] == "bunker"
        )
        assert calibrated["duration_minutes"] == 75
        assert calibrated["source_id"] == "recorded-bunker-calibration-api"
        assert all(
            step["duration_minutes"] == 75
            for step in harbor["service_steps"]
            if step["kind"] == "bunker"
        )

        source = next(
            row for row in harbor["data_sources"]
            if row["source_id"] == "recorded-bunker-calibration-api"
        )
        assert source["domain"] == "service_calibration"
        assert source["mode"] == "recorded"

        ledger = client.get("/api/v1/events?limit=50").json()
        event = next(
            row for row in ledger
            if row["category"] == "service_calibration"
        )
        assert event["actor_id"] == "operator-17"
        assert event["actor_role"] == "operator"
        assert event["source_id"] == "recorded-bunker-calibration-api"

        stale_payload = {
            **payload,
            "duration_minutes": 90,
            "source_id": "stale-bunker-calibration-api",
            "observed_at": (now - timedelta(days=2)).isoformat(),
            "stale_after_seconds": 60,
        }
        stale = client.post(
            "/api/v1/service-duration-calibrations",
            json=stale_payload,
            headers=auth_headers(OPERATOR_TOKEN),
        )
        assert stale.status_code == 409

        after_stale = client.get("/api/v1/harbor").json()
        bunker_after_stale = next(
            row for row in after_stale["service_duration_calibrations"]
            if row["service_kind"] == "bunker"
        )
        assert bunker_after_stale["duration_minutes"] == 75
        assert bunker_after_stale["source_id"] == "recorded-bunker-calibration-api"


def test_stale_recovery_apply_returns_ranked_contingency_contract():
    with TestClient(app) as client:
        payload = client.post(
            "/api/v1/scenarios/bunker-loss/run"
        ).json()

        stale = next(
            proposal
            for proposal in payload["recovery_proposals"]
            if any(
                action.get("to_resource_id") == "bunker-barge-12"
                for action in proposal["actions"]
            )
        )

        failed_backup = client.post(
            "/api/v1/incidents",
            json={
                "incident_type": "bunker_unavailable",
                "target_port_call_id": "pc-aurora",
                "target_resource_id": "bunker-barge-12",
                "impact_minutes": 0,
            },
        )
        assert failed_backup.status_code == 200
        assert failed_backup.json()["target_resource_id"] == "bunker-barge-12"
        assert failed_backup.json()["impact_minutes"] == 0

        stale_apply = client.post(
            f"/api/v1/recovery/proposals/{stale['id']}/apply",
            headers=auth_headers(OPERATOR_TOKEN),
        )
        assert stale_apply.status_code == 409
        detail = stale_apply.json()["detail"]
        assert detail["code"] == "recovery_proposal_stale"
        assert detail["stale_proposal_id"] == stale["id"]
        assert detail["target_port_call_id"] == "pc-aurora"
        assert detail["unavailable_resource_ids"] == ["bunker-barge-12"]
        assert detail["auto_apply"] is False
        assert detail["current_state_fingerprint"] != detail["stale_state_fingerprint"]

        replacements = detail["replacement_proposals"]
        assert replacements
        assert all(
            action.get("to_resource_id") != "bunker-barge-12"
            for proposal in replacements
            for action in proposal["actions"]
        )
        replacement = next(
            proposal
            for proposal in replacements
            if any(
                action.get("to_resource_id") == "bunker-barge-9"
                for action in proposal["actions"]
            )
        )

        before = client.get(
            "/api/v1/port-calls/pc-aurora/dependency-graph"
        ).json()
        before_nodes = {
            node["kind"]: node
            for node in before["nodes"]
        }
        assert before_nodes["bunker"]["state"] == "blocked"

        applied = client.post(
            f"/api/v1/recovery/proposals/{replacement['id']}/apply",
            headers=auth_headers(OPERATOR_TOKEN),
        )
        assert applied.status_code == 200
        assert applied.json()["resulting_blocked_services"] == 0

        after = client.get(
            "/api/v1/port-calls/pc-aurora/dependency-graph"
        ).json()
        after_nodes = {
            node["kind"]: node
            for node in after["nodes"]
        }
        assert after_nodes["bunker"]["state"] != "blocked"
        assert after_nodes["departure"]["state"] != "blocked"


def test_readiness_reports_runtime_and_schema_contract():
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {
            "ok": True,
            "service": "portflow-api",
            "version": "0.17.0",
        }

        ready = client.get("/readyz")
        assert ready.status_code == 200
        payload = ready.json()
        assert payload["ok"] is True
        assert payload["runtime_ready"] is True
        assert payload["schema_mode"] == "migrate"
        assert payload["schema"]["database_reachable"] is True
        assert payload["schema"]["compatible"] is True
        assert payload["schema"]["current_version"] == 3
        assert payload["schema"]["expected_version"] == 3


def _metric_value(payload: str, name: str) -> float:
    prefix = name + " "
    for line in payload.splitlines():
        if line.startswith(prefix):
            return float(line[len(prefix):])
    raise AssertionError(f"missing metric {name}")


def test_metrics_expose_runtime_domain_counters_and_route_templates():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        before = client.get("/metrics")
        assert before.status_code == 200
        assert before.headers["content-type"].startswith(
            "text/plain; version=0.0.4"
        )
        before_text = before.text
        assert _metric_value(before_text, "portflow_runtime_ready") == 1
        assert _metric_value(before_text, "portflow_schema_compatible") == 1

        scenario_before = _metric_value(
            before_text,
            "portflow_scenario_runs_total",
        )
        run = client.post("/api/v1/scenarios/bunker-loss/run")
        assert run.status_code == 200

        risk = client.get("/api/v1/port-calls/pc-aurora/risk")
        assert risk.status_code == 200

        after = client.get("/metrics")
        assert after.status_code == 200
        after_text = after.text

        assert _metric_value(
            after_text,
            "portflow_scenario_runs_total",
        ) == scenario_before + 1
        assert 'route="/api/v1/port-calls/{call_id}/risk"' in after_text
        assert 'route="/api/v1/port-calls/pc-aurora/risk"' not in after_text
        assert "portflow_active_incidents 1" in after_text
        assert "portflow_http_requests_total" in after_text


def test_http_request_log_is_structured_json(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with TestClient(app) as client:
            response = client.get("/healthz")

    assert response.status_code == 200
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "uvicorn.error"
        and record.message.startswith("{")
    ]
    health = next(
        record
        for record in records
        if record.get("route") == "/healthz"
    )
    assert health["event"] == "http_request"
    assert health["method"] == "GET"
    assert health["status"] == 200
    assert isinstance(health["duration_ms"], (int, float))
    assert health["duration_ms"] >= 0
    assert health["timestamp"].endswith("+00:00")


def test_scenario_and_recovery_evidence_are_durable_authenticated_audit_surfaces():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        run = client.post("/api/v1/scenarios/bunker-loss/run")
        assert run.status_code == 200
        run_payload = run.json()
        run_id = run_payload["evidence_run_id"]
        assert run_id.startswith("scenario-run-")

        anonymous = client.get("/api/v1/evidence/scenario-runs")
        assert anonymous.status_code == 401

        scenario_evidence = client.get(
            "/api/v1/evidence/scenario-runs",
            params={"scenario_id": "bunker-loss", "limit": 50},
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert scenario_evidence.status_code == 200
        runs = scenario_evidence.json()["evidence"]
        matched = next(item for item in runs if item["run_id"] == run_id)
        assert matched["scenario"]["id"] == "bunker-loss"
        assert matched["harbor"]["metrics"]["active_incidents"] == 1
        assert matched["recovery_proposals"]

        proposal_evidence = client.get(
            "/api/v1/evidence/recovery-proposals",
            params={"limit": 100},
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert proposal_evidence.status_code == 200
        batches = proposal_evidence.json()["evidence"]
        scenario_batches = [
            batch
            for batch in batches
            if batch["trigger"] == "scenario"
        ]
        assert scenario_batches
        assert any(
            proposal["id"]
            in {
                expected["id"]
                for expected in matched["recovery_proposals"]
            }
            for batch in scenario_batches
            for proposal in batch["proposals"]
        )

        pack = client.get(
            f"/api/v1/evidence/scenario-runs/{run_id}/pack",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert pack.status_code == 200
        pack_payload = pack.json()
        assert pack_payload["pack_version"] == "portflow-evidence-v1"
        assert len(pack_payload["sha256"]) == 64
        assert pack_payload["scenario_run"]["run_id"] == run_id
        assert pack_payload["replay_input"]["scenario_id"] == "bunker-loss"
        assert pack_payload["replay_input"]["actions"]

        pack_again = client.get(
            f"/api/v1/evidence/scenario-runs/{run_id}/pack",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert pack_again.json()["sha256"] == pack_payload["sha256"]

        client.post("/api/v1/demo/reset")

        after_reset = client.get(
            "/api/v1/evidence/scenario-runs",
            params={"scenario_id": "bunker-loss", "limit": 50},
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert any(
            item["run_id"] == run_id
            for item in after_reset.json()["evidence"]
        )

        missing_pack = client.get(
            "/api/v1/evidence/scenario-runs/does-not-exist/pack",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert missing_pack.status_code == 404


def test_public_portfolio_mode_hides_metrics(monkeypatch):
    monkeypatch.setenv("PORTFLOW_PUBLIC_MODE", "1")
    with TestClient(app) as client:
        response = client.get("/metrics")
    assert response.status_code == 404


def test_vessel_runtime_contract_is_advisory_and_versioned():
    with TestClient(app) as client:
        response = client.get("/api/v1/integration/contracts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_contract"] == "portflow.vessel-event.v1"
    assert payload["coordination_contract"] == "portflow.coordination.v1"
    assert payload["invariants"]["raw_sensor_streams_owned_by_vessel_runtime"] is True
    assert payload["invariants"]["portflow_accepts_normalized_events_only"] is True
    assert payload["invariants"]["coordination_is_advisory_only"] is True
    assert payload["invariants"]["human_approval_required_for_recovery"] is True
    assert payload["invariants"]["direct_actuation_allowed"] is False


def test_vessel_runtime_event_ingest_is_scoped_durable_and_idempotent():
    event = {
        "contract_version": "portflow.vessel-event.v1",
        "event_id": f"evt-aurora-{uuid4().hex[:16]}",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "vessel_id": "v-aurora",
        "port_call_id": "pc-aurora",
        "event_type": "readiness",
        "sequence": 41,
        "source_system": "aurora-edge-runtime",
        "payload": {
            "navigation_ready": True,
            "cargo_ready": False,
            "normalized_note": "awaiting terminal release",
        },
        "evidence_refs": ["edge-log-41"],
    }

    with TestClient(app) as client:
        missing = client.post(
            "/api/v1/integration/vessel-events",
            json=event,
        )
        assert missing.status_code == 401

        first = client.post(
            "/api/v1/integration/vessel-events",
            headers=auth_headers(INTEGRATION_TOKEN),
            json=event,
        )
        assert first.status_code == 200
        assert first.json()["duplicate"] is False

        duplicate = client.post(
            "/api/v1/integration/vessel-events",
            headers=auth_headers(INTEGRATION_TOKEN),
            json=event,
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["accepted_at"] == first.json()["accepted_at"]

        listed = client.get(
            "/api/v1/integration/vessel-events",
            headers=auth_headers(INTEGRATION_TOKEN),
        )
        assert listed.status_code == 200
        rows = listed.json()["events"]
        match = next(
            row for row in rows
            if row["event"]["event_id"] == event["event_id"]
        )
        assert match["integration_id"] == "vessel-runtime-aurora"
        assert match["event"]["sequence"] == 41

        changed = dict(event)
        changed["payload"] = {"navigation_ready": False}
        conflict = client.post(
            "/api/v1/integration/vessel-events",
            headers=auth_headers(INTEGRATION_TOKEN),
            json=changed,
        )
        assert conflict.status_code == 409


def test_vessel_runtime_identity_is_vessel_scoped_and_not_an_operator():
    unauthorized = {
        "contract_version": "portflow.vessel-event.v1",
        "event_id": "evt-other-vessel-0001",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "vessel_id": "v-glory",
        "port_call_id": "pc-glory",
        "event_type": "eta",
        "sequence": 1,
        "source_system": "other-edge-runtime",
        "payload": {"eta_minutes": 12},
    }

    with TestClient(app) as client:
        denied = client.post(
            "/api/v1/integration/vessel-events",
            headers=auth_headers(INTEGRATION_TOKEN),
            json=unauthorized,
        )
        assert denied.status_code == 403

        client.post("/api/v1/demo/reset")
        scenario = client.post(
            "/api/v1/scenarios/bunker-loss/run"
        ).json()
        proposal_id = scenario["recovery_proposals"][0]["id"]

        apply_attempt = client.post(
            f"/api/v1/recovery/proposals/{proposal_id}/apply",
            headers=auth_headers(INTEGRATION_TOKEN),
        )
        assert apply_attempt.status_code == 401


def test_vessel_coordination_snapshot_is_advisory_only():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.get(
            "/api/v1/integration/port-calls/pc-aurora/coordination",
            headers=auth_headers(INTEGRATION_TOKEN),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "portflow.coordination.v1"
    assert payload["port_call_id"] == "pc-aurora"
    assert payload["vessel_id"] == "v-aurora"
    assert payload["advisory_only"] is True
    assert payload["requires_human_approval"] is True
    assert payload["actuation_allowed"] is False
    assert all(
        proposal["requires_approval"] is True
        for proposal in payload["recovery_proposals"]
    )



def _crew_exception_wire_event(
    *,
    exception_ref: str,
    runtime_event_type: str,
    state: str,
    sequence: int,
    occurred_at: datetime,
    vessel_id: str = "v-aurora",
    port_call_id: str | None = "pc-aurora",
) -> dict[str, object]:
    return {
        "contract_version": "portflow.vessel-event.v1",
        "event_id": f"evt-crew-exception-{sequence}-{uuid4().hex[:12]}",
        "occurred_at": occurred_at.isoformat(),
        "vessel_id": vessel_id,
        "port_call_id": port_call_id,
        "event_type": "constraint",
        "sequence": sequence,
        "source_system": f"maritime-runtime:{vessel_id}",
        "payload": {
            "runtime_event_type": runtime_event_type,
            "title": "producer-controlled title must not pass through",
            "summary": "producer-controlled private text must not pass through",
            "risk": "critical",
            "source_sequence": sequence,
            "exception_ref": exception_ref,
            "category": "crew_operational_exception",
            "state": state,
            "privacy_minimized": True,
            "advisory_only": True,
            "execution_authorized": False,
            # Deliberate accidental/private expansion. Shore projection must
            # never echo these fields into the human exception view.
            "actor_id": "second-engineer",
            "task_id": "private-duty-task",
            "declared_minutes": 240,
            "evidence_minutes": 300,
            "override_reason": "private local reason",
        },
        "evidence_refs": [],
    }


def test_operator_vessel_exception_view_aggregates_current_v078_lifecycle_privately():
    exception_ref = "mrt-exception-" + uuid4().hex[:20]
    base = datetime.now(timezone.utc).replace(microsecond=0)
    lifecycle = [
        ("crew.exception.opened", "open"),
        ("crew.attention.acknowledged", "acknowledged"),
        ("crew.attention.claimed", "claimed"),
        ("crew.exception.override_recorded", "override_recorded"),
        ("crew.attention.resolved", "resolved"),
    ]
    events = [
        _crew_exception_wire_event(
            exception_ref=exception_ref,
            runtime_event_type=event_type,
            state=state,
            sequence=900 + index,
            occurred_at=base + timedelta(seconds=index),
        )
        for index, (event_type, state) in enumerate(lifecycle)
    ]

    with TestClient(app) as client:
        for event in events:
            response = client.post(
                "/api/v1/integration/vessel-events",
                headers=auth_headers(INTEGRATION_TOKEN),
                json=event,
            )
            assert response.status_code == 200

        assert client.get(
            "/api/v1/operations/vessel-exceptions"
        ).status_code == 401
        assert client.get(
            "/api/v1/operations/vessel-exceptions",
            headers=auth_headers(INTEGRATION_TOKEN),
        ).status_code == 401

        viewed = client.get(
            "/api/v1/operations/vessel-exceptions",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert viewed.status_code == 200
        body = viewed.json()
        match = next(
            item
            for item in body["exceptions"]
            if item["exception_ref"] == exception_ref
        )

    assert match["vessel_id"] == "v-aurora"
    assert match["port_call_id"] == "pc-aurora"
    assert match["state"] == "resolved"
    assert match["risk"] == "low"
    assert match["title"] == "Crew operational exception resolved"
    assert match["privacy_minimized"] is True
    assert match["advisory_only"] is True
    assert match["execution_authorized"] is False
    assert match["first_source_sequence"] == 900
    assert match["latest_source_sequence"] == 904
    assert datetime.fromisoformat(
        match["opened_at"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(str(events[0]["occurred_at"]))
    assert datetime.fromisoformat(
        match["updated_at"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(str(events[-1]["occurred_at"]))
    assert [row["state"] for row in match["history"]] == [
        "open",
        "acknowledged",
        "claimed",
        "override_recorded",
        "resolved",
    ]
    assert [row["source_sequence"] for row in match["history"]] == [
        900,
        901,
        902,
        903,
        904,
    ]

    rendered = json.dumps(match).lower()
    for forbidden in (
        "second-engineer",
        "private-duty-task",
        "private local reason",
        "declared_minutes",
        "evidence_minutes",
        "producer-controlled",
        "source_entry_hash",
        "maritime-ledger:",
        "evidence_refs",
        "integration_id",
        "source_system",
    ):
        assert forbidden not in rendered


def test_operator_vessel_exception_view_rejects_malformed_or_non_v078_contracts():
    base = datetime.now(timezone.utc).replace(microsecond=0)
    exception_ref = "mrt-exception-" + uuid4().hex[:20]
    malformed = _crew_exception_wire_event(
        exception_ref=exception_ref,
        runtime_event_type="crew.exception.opened",
        state="open",
        sequence=980,
        occurred_at=base,
    )
    malformed["evidence_refs"] = ["maritime-ledger:" + "a" * 64]

    unrelated = _crew_exception_wire_event(
        exception_ref="mrt-exception-" + uuid4().hex[:20],
        runtime_event_type="equipment.unavailable",
        state="open",
        sequence=981,
        occurred_at=base + timedelta(seconds=1),
    )

    with TestClient(app) as client:
        for event in (malformed, unrelated):
            assert client.post(
                "/api/v1/integration/vessel-events",
                headers=auth_headers(INTEGRATION_TOKEN),
                json=event,
            ).status_code == 200

        viewed = client.get(
            "/api/v1/operations/vessel-exceptions",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert viewed.status_code == 200

    refs = {
        item["exception_ref"]
        for item in viewed.json()["exceptions"]
    }
    assert exception_ref not in refs
    assert unrelated["payload"]["exception_ref"] not in refs


def test_operator_vessel_exception_view_rejects_state_after_resolution():
    exception_ref = "mrt-exception-" + uuid4().hex[:20]
    base = datetime.now(timezone.utc).replace(microsecond=0)
    lifecycle = [
        ("crew.exception.opened", "open"),
        ("crew.attention.acknowledged", "acknowledged"),
        ("crew.attention.claimed", "claimed"),
        ("crew.attention.resolved", "resolved"),
        ("crew.attention.claimed", "claimed"),
    ]

    with TestClient(app) as client:
        for index, (event_type, state) in enumerate(lifecycle):
            response = client.post(
                "/api/v1/integration/vessel-events",
                headers=auth_headers(INTEGRATION_TOKEN),
                json=_crew_exception_wire_event(
                    exception_ref=exception_ref,
                    runtime_event_type=event_type,
                    state=state,
                    sequence=990 + index,
                    occurred_at=base + timedelta(seconds=index),
                ),
            )
            assert response.status_code == 200

        viewed = client.get(
            "/api/v1/operations/vessel-exceptions",
            headers=auth_headers(VIEWER_TOKEN),
        )
        assert viewed.status_code == 200

    refs = {
        item["exception_ref"]
        for item in viewed.json()["exceptions"]
    }
    assert exception_ref not in refs


def _crew_exception_record(
    *,
    integration_id: str,
    exception_ref: str,
    runtime_event_type: str,
    state: str,
    sequence: int,
    occurred_at: datetime,
    vessel_id: str = "v-aurora",
    port_call_id: str | None = "pc-aurora",
) -> VesselRuntimeEventRecord:
    event = VesselRuntimeEvent.model_validate(
        _crew_exception_wire_event(
            exception_ref=exception_ref,
            runtime_event_type=runtime_event_type,
            state=state,
            sequence=sequence,
            occurred_at=occurred_at,
            vessel_id=vessel_id,
            port_call_id=port_call_id,
        )
    )
    return VesselRuntimeEventRecord(
        event=event,
        integration_id=integration_id,
        received_at=occurred_at + timedelta(milliseconds=100),
    )


def test_operator_vessel_exception_view_scopes_same_ref_by_vessel(
    monkeypatch,
):
    exception_ref = "mrt-exception-" + "a" * 20
    base = datetime.now(timezone.utc).replace(microsecond=0)
    records = [
        _crew_exception_record(
            integration_id="runtime-aurora",
            exception_ref=exception_ref,
            runtime_event_type="crew.exception.opened",
            state="open",
            sequence=100,
            occurred_at=base,
            vessel_id="v-aurora",
            port_call_id="pc-aurora",
        ),
        _crew_exception_record(
            integration_id="runtime-aurora",
            exception_ref=exception_ref,
            runtime_event_type="crew.attention.acknowledged",
            state="acknowledged",
            sequence=101,
            occurred_at=base + timedelta(seconds=1),
            vessel_id="v-aurora",
            port_call_id="pc-aurora",
        ),
        _crew_exception_record(
            integration_id="runtime-glory",
            exception_ref=exception_ref,
            runtime_event_type="crew.exception.opened",
            state="open",
            sequence=200,
            occurred_at=base + timedelta(seconds=2),
            vessel_id="v-glory",
            port_call_id="pc-glory",
        ),
        _crew_exception_record(
            integration_id="runtime-glory",
            exception_ref=exception_ref,
            runtime_event_type="crew.attention.acknowledged",
            state="acknowledged",
            sequence=201,
            occurred_at=base + timedelta(seconds=3),
            vessel_id="v-glory",
            port_call_id="pc-glory",
        ),
    ]
    monkeypatch.setattr(
        main_module.store,
        "list_vessel_runtime_events",
        lambda **_: records,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/operations/vessel-exceptions",
            headers=auth_headers(VIEWER_TOKEN),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert {
        (item["vessel_id"], item["exception_ref"], item["state"])
        for item in body["exceptions"]
    } == {
        ("v-aurora", exception_ref, "acknowledged"),
        ("v-glory", exception_ref, "acknowledged"),
    }


def test_operator_vessel_exception_view_fails_closed_on_oversized_lifecycle(
    monkeypatch,
):
    exception_ref = "mrt-exception-" + "b" * 20
    base = datetime.now(timezone.utc).replace(microsecond=0)
    records = [
        _crew_exception_record(
            integration_id="runtime-aurora",
            exception_ref=exception_ref,
            runtime_event_type="crew.exception.opened",
            state="open",
            sequence=300,
            occurred_at=base,
        ),
        _crew_exception_record(
            integration_id="runtime-aurora",
            exception_ref=exception_ref,
            runtime_event_type="crew.attention.acknowledged",
            state="acknowledged",
            sequence=301,
            occurred_at=base + timedelta(seconds=1),
        ),
    ]
    for index in range(2, 65):
        claimed = index % 2 == 0
        records.append(
            _crew_exception_record(
                integration_id="runtime-aurora",
                exception_ref=exception_ref,
                runtime_event_type=(
                    "crew.attention.claimed"
                    if claimed
                    else "crew.attention.released"
                ),
                state="claimed" if claimed else "released",
                sequence=300 + index,
                occurred_at=base + timedelta(seconds=index),
            )
        )
    monkeypatch.setattr(
        main_module.store,
        "list_vessel_runtime_events",
        lambda **_: records,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/operations/vessel-exceptions",
            headers=auth_headers(VIEWER_TOKEN),
        )

    assert response.status_code == 200
    assert response.json()["exceptions"] == []
