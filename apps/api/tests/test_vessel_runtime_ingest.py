from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from portflow_api.models import (
    OperationsEvent,
    RiskLevel,
    VesselRuntimeEnvelope,
    VesselRuntimeProjectedEvent,
)
from portflow_api.storage import OperationsStore


def make_store(tmp_path: Path) -> OperationsStore:
    store = OperationsStore(f"sqlite:///{tmp_path / 'runtime-ingest.db'}")
    store.init_schema()
    return store


def operations_event(
    *,
    event_id: str = "mrt-vessel-alpha-1-event",
    runtime_id: str = "vessel-alpha",
) -> OperationsEvent:
    return OperationsEvent(
        id=event_id,
        occurred_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        category="equipment",
        severity=RiskLevel.HIGH,
        title="Equipment Unavailable",
        message="generator-1 unavailable",
        vessel_id=runtime_id,
        source_id=f"maritime-runtime:{runtime_id}",
    )


def envelope(
    *,
    runtime_id: str = "vessel-alpha",
    after_sequence: int = 0,
    base_hash: str = "0" * 64,
    last_sequence: int = 3,
    head_hash: str = "a" * 64,
    include_event: bool = True,
) -> VesselRuntimeEnvelope:
    events = []
    if include_event:
        events.append(
            VesselRuntimeProjectedEvent(
                source_sequence=1,
                source_entry_hash="1" * 64,
                event=operations_event(runtime_id=runtime_id),
            )
        )
    return VesselRuntimeEnvelope(
        vessel_runtime_id=runtime_id,
        source_mode="synthetic",
        after_sequence=after_sequence,
        base_source_hash=base_hash,
        last_source_sequence=last_sequence,
        source_head_hash=head_hash,
        events=events,
        excluded_by_policy=max(0, last_sequence - len(events)),
    )


def test_store_accepts_duplicate_gap_conflict_and_privacy_only_advance(tmp_path: Path):
    store = make_store(tmp_path)

    first = store.ingest_vessel_runtime_envelope(envelope())
    assert first.status.value == "accepted"
    assert first.accepted_events == 1
    assert store.vessel_runtime_cursor("vessel-alpha") == (3, "a" * 64)

    duplicate = store.ingest_vessel_runtime_envelope(envelope())
    assert duplicate.status.value == "duplicate"
    assert duplicate.accepted_events == 0

    gap = store.ingest_vessel_runtime_envelope(
        envelope(
            after_sequence=4,
            base_hash="b" * 64,
            last_sequence=5,
            head_hash="c" * 64,
            include_event=False,
        )
    )
    assert gap.status.value == "gap"

    conflict = store.ingest_vessel_runtime_envelope(
        envelope(
            after_sequence=3,
            base_hash="f" * 64,
            last_sequence=4,
            head_hash="b" * 64,
            include_event=False,
        )
    )
    assert conflict.status.value == "conflict"

    privacy_only = store.ingest_vessel_runtime_envelope(
        envelope(
            after_sequence=3,
            base_hash="a" * 64,
            last_sequence=4,
            head_hash="b" * 64,
            include_event=False,
        )
    )
    assert privacy_only.status.value == "accepted"
    assert privacy_only.accepted_events == 0
    assert store.vessel_runtime_cursor("vessel-alpha") == (4, "b" * 64)


def test_envelope_rejects_mismatched_runtime_identity():
    import pytest

    with pytest.raises(ValueError, match="vessel_id"):
        VesselRuntimeEnvelope(
            vessel_runtime_id="vessel-alpha",
            source_mode="synthetic",
            after_sequence=0,
            base_source_hash="0" * 64,
            last_source_sequence=1,
            source_head_hash="a" * 64,
            events=[
                VesselRuntimeProjectedEvent(
                    source_sequence=1,
                    source_entry_hash="1" * 64,
                    event=operations_event(runtime_id="other-vessel"),
                )
            ],
        )


RUNTIME_TOKEN = "vessel-runtime-test-token"
os.environ["PORTFLOW_VESSEL_RUNTIMES_JSON"] = json.dumps([
    {
        "token_sha256": hashlib.sha256(RUNTIME_TOKEN.encode()).hexdigest(),
        "vessel_runtime_id": "vessel-alpha-api",
        "display_name": "MV Alpha Edge",
    }
])

from portflow_api.main import app


def test_api_requires_edge_auth_and_ingests_projection():
    runtime_id = "vessel-alpha-api"
    payload = envelope(runtime_id=runtime_id).model_dump(mode="json")

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        unauth = client.post("/api/v1/vessel-runtime/ingest", json=payload)
        assert unauth.status_code == 401

        accepted = client.post(
            "/api/v1/vessel-runtime/ingest",
            json=payload,
            headers={"Authorization": "Bearer " + RUNTIME_TOKEN},
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        assert accepted.json()["accepted_events"] == 1

        duplicate = client.post(
            "/api/v1/vessel-runtime/ingest",
            json=payload,
            headers={"Authorization": "Bearer " + RUNTIME_TOKEN},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "duplicate"

        events = client.get("/api/v1/events?limit=50").json()
        imported = [event for event in events if event["source_id"] == f"maritime-runtime:{runtime_id}"]
        assert len(imported) == 1
        assert imported[0]["title"] == "Equipment Unavailable"


def test_api_rejects_runtime_id_not_bound_to_credential():
    payload = envelope(runtime_id="different-vessel").model_dump(mode="json")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/vessel-runtime/ingest",
            json=payload,
            headers={"Authorization": "Bearer " + RUNTIME_TOKEN},
        )
        assert response.status_code == 403
