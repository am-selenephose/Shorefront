from datetime import datetime, timedelta, timezone

from portflow_api.adapters import HttpJsonAdapter, configured_live_adapters
from portflow_api.models import DataDomain


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
