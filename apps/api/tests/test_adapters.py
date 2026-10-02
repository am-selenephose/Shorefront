from datetime import datetime, timedelta, timezone

from shorefront_api.adapters import HttpJsonAdapter, configured_live_adapters
from shorefront_api.models import DataDomain


def test_live_http_adapter_normalizes_fresh_payload():
    now = datetime(2026, 9, 21, 2, 0, tzinfo=timezone.utc)

    def loader(url: str, timeout: float) -> dict:
        assert url == "https://example.invalid/ais"
        assert timeout == 2.0
        return {
            "observed_at": (now - timedelta(seconds=15)).isoformat(),
            "records": [{"vessel_id": "v-aurora", "lat": 51.9, "lon": 4.0}],
        }

    adapter = HttpJsonAdapter(
        adapter_id="live-ais-test",
        domain=DataDomain.AIS,
        provider="Test AIS",
        url="https://example.invalid/ais",
        stale_after_seconds=120,
        loader=loader,
    )
    snapshot = adapter.snapshot(now=now)

    assert snapshot.provenance.mode.value == "live"
    assert snapshot.provenance.health.value == "healthy"
    assert snapshot.provenance.freshness_seconds == 15
    assert snapshot.provenance.stale is False
    assert snapshot.provenance.record_count == 1


def test_live_http_adapter_marks_old_observation_stale():
    now = datetime(2026, 9, 21, 2, 0, tzinfo=timezone.utc)

    adapter = HttpJsonAdapter(
        adapter_id="live-weather-test",
        domain=DataDomain.WEATHER_TIDE,
        provider="Test Weather",
        url="https://example.invalid/weather",
        stale_after_seconds=300,
        loader=lambda url, timeout: {
            "observed_at": (now - timedelta(seconds=901)).isoformat(),
            "records": [{"wind_knots": 12}],
        },
    )
    snapshot = adapter.snapshot(now=now)

    assert snapshot.provenance.health.value == "stale"
    assert snapshot.provenance.stale is True
    assert snapshot.provenance.freshness_seconds == 901


def test_live_http_adapter_converts_loader_failure_to_error_health():
    def broken_loader(url: str, timeout: float) -> dict:
        raise TimeoutError("simulated timeout")

    adapter = HttpJsonAdapter(
        adapter_id="live-berth-test",
        domain=DataDomain.BERTH_PLAN,
        provider="Test TOS",
        url="https://example.invalid/berths",
        stale_after_seconds=600,
        loader=broken_loader,
    )
    snapshot = adapter.snapshot()

    assert snapshot.provenance.mode.value == "live"
    assert snapshot.provenance.health.value == "error"
    assert snapshot.provenance.stale is True
    assert snapshot.provenance.record_count == 0
    assert "TimeoutError" in (snapshot.provenance.detail or "")


def test_live_adapter_registry_only_includes_configured_urls(monkeypatch):
    for name in ("PORTFLOW_AIS_URL", "PORTFLOW_WEATHER_URL", "PORTFLOW_BERTH_PLAN_URL"):
        monkeypatch.delenv(name, raising=False)

    assert configured_live_adapters() == {}

    monkeypatch.setenv("PORTFLOW_AIS_URL", "https://feeds.example.test/ais")
    monkeypatch.setenv("PORTFLOW_AIS_PROVIDER", "Example AIS")

    adapters = configured_live_adapters()
    assert set(adapters) == {"live-ais"}
    assert adapters["live-ais"].provider == "Example AIS"


def test_live_adapter_backoff_suppresses_early_retry_and_resets_on_success():
    base = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
    calls = {"count": 0}
    recovery_observed_at = {"value": base}

    def loader(url: str, timeout: float) -> dict:
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("first attempt fails")
        return {
            "observed_at": recovery_observed_at["value"].isoformat(),
            "records": [{"vessel_id": "v-aurora", "lat": 51.9, "lon": 4.0}],
        }

    adapter = HttpJsonAdapter(
        adapter_id="live-backoff-reset-test",
        domain=DataDomain.AIS,
        provider="Backoff Test",
        url="https://example.invalid/ais",
        stale_after_seconds=120,
        retry_base_seconds=10,
        retry_max_seconds=60,
        retry_jitter_fraction=0.0,
        loader=loader,
    )

    failed = adapter.snapshot(now=base)
    assert calls["count"] == 1
    assert failed.provenance.health.value == "error"
    assert failed.provenance.consecutive_errors == 1
    assert failed.provenance.last_attempt_at == base
    assert failed.provenance.retry_delay_seconds == 10
    assert failed.provenance.next_retry_at == base + timedelta(seconds=10)

    suppressed = adapter.snapshot(now=base + timedelta(seconds=5))
    assert calls["count"] == 1
    assert suppressed.provenance.consecutive_errors == 1
    assert suppressed.provenance.last_attempt_at == base
    assert suppressed.provenance.next_retry_at == failed.provenance.next_retry_at
    assert "Retry backoff active" in (suppressed.provenance.detail or "")

    due = failed.provenance.next_retry_at
    assert due is not None
    recovery_observed_at["value"] = due
    recovered = adapter.snapshot(now=due)

    assert calls["count"] == 2
    assert recovered.provenance.health.value == "healthy"
    assert recovered.provenance.consecutive_errors == 0
    assert recovered.provenance.last_attempt_at == due
    assert recovered.provenance.next_retry_at is None
    assert recovered.provenance.retry_delay_seconds == 0


def test_live_adapter_backoff_grows_exponentially_and_caps():
    base = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
    adapter = HttpJsonAdapter(
        adapter_id="live-backoff-cap-test",
        domain=DataDomain.AIS,
        provider="Backoff Test",
        url="https://example.invalid/ais",
        stale_after_seconds=120,
        retry_base_seconds=10,
        retry_max_seconds=25,
        retry_jitter_fraction=0.0,
        loader=lambda url, timeout: (_ for _ in ()).throw(TimeoutError("down")),
    )

    first = adapter.snapshot(now=base)
    assert first.provenance.retry_delay_seconds == 10

    second_at = first.provenance.next_retry_at
    assert second_at is not None
    second = adapter.snapshot(now=second_at)
    assert second.provenance.consecutive_errors == 2
    assert second.provenance.retry_delay_seconds == 20

    third_at = second.provenance.next_retry_at
    assert third_at is not None
    third = adapter.snapshot(now=third_at)
    assert third.provenance.consecutive_errors == 3
    assert third.provenance.retry_delay_seconds == 25

    fourth_at = third.provenance.next_retry_at
    assert fourth_at is not None
    fourth = adapter.snapshot(now=fourth_at)
    assert fourth.provenance.consecutive_errors == 4
    assert fourth.provenance.retry_delay_seconds == 25


def test_live_adapter_retry_jitter_is_deterministic_and_bounded():
    adapter = HttpJsonAdapter(
        adapter_id="live-jitter-test",
        domain=DataDomain.AIS,
        provider="Jitter Test",
        url="https://example.invalid/ais",
        stale_after_seconds=120,
        retry_base_seconds=100,
        retry_max_seconds=1000,
        retry_jitter_fraction=0.2,
    )

    first = adapter._retry_delay_for_error(1)
    again = adapter._retry_delay_for_error(1)
    second = adapter._retry_delay_for_error(2)

    assert first == again
    assert 80 <= first <= 120
    assert 160 <= second <= 240
    assert adapter._retry_delay_for_error(20) <= 1000
