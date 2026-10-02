from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from threading import Lock
from typing import Callable, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import (
    AdapterHealth,
    AdapterSnapshot,
    DataDomain,
    DataSourceMode,
    DataSourceProvenance,
)


class ExternalDataAdapter(Protocol):
    adapter_id: str
    domain: DataDomain

    def snapshot(self, now: datetime | None = None) -> AdapterSnapshot:
        ...


@dataclass(frozen=True)
class RecordedFixtureAdapter:
    adapter_id: str
    domain: DataDomain
    provider: str
    stale_after_seconds: int
    age_seconds: int
    records: list[dict]
    detail: str

    def snapshot(self, now: datetime | None = None) -> AdapterSnapshot:
        received_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)
        observed_at = received_at - timedelta(seconds=self.age_seconds)
        stale = self.age_seconds > self.stale_after_seconds
        health = AdapterHealth.STALE if stale else AdapterHealth.HEALTHY

        provenance = DataSourceProvenance(
            source_id=self.adapter_id,
            domain=self.domain,
            mode=DataSourceMode.RECORDED,
            provider=self.provider,
            observed_at=observed_at,
            received_at=received_at,
            freshness_seconds=self.age_seconds,
            stale_after_seconds=self.stale_after_seconds,
            stale=stale,
            health=health,
            record_count=len(self.records),
            detail=self.detail,
        )
        return AdapterSnapshot(
            adapter_id=self.adapter_id,
            provenance=provenance,
            records=[dict(item) for item in self.records],
        )


JsonLoader = Callable[[str, float], dict]


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_live_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise ValueError("Live adapter URL must use HTTPS, except loopback HTTP for development")


def _http_json_loader(url: str, timeout_seconds: float) -> dict:
    _validate_live_url(url)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Shorefront/adapter",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Live adapter payload must be a JSON object")
    return payload


@dataclass
class HttpJsonAdapter:
    adapter_id: str
    domain: DataDomain
    provider: str
    url: str
    stale_after_seconds: int
    timeout_seconds: float = 2.0
    retry_base_seconds: int = 5
    retry_max_seconds: int = 300
    retry_jitter_fraction: float = 0.2
    loader: JsonLoader = _http_json_loader
    _last_good_snapshot: AdapterSnapshot | None = field(default=None, init=False, repr=False, compare=False)
    _last_success_at: datetime | None = field(default=None, init=False, repr=False, compare=False)
    _last_attempt_at: datetime | None = field(default=None, init=False, repr=False, compare=False)
    _next_retry_at: datetime | None = field(default=None, init=False, repr=False, compare=False)
    _retry_delay_seconds: int = field(default=0, init=False, repr=False, compare=False)
    _consecutive_errors: int = field(default=0, init=False, repr=False, compare=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def config_key(self) -> tuple:
        return (
            self.adapter_id,
            self.domain,
            self.provider,
            self.url,
            self.stale_after_seconds,
            self.timeout_seconds,
            self.retry_base_seconds,
            self.retry_max_seconds,
            self.retry_jitter_fraction,
        )

    def _retry_delay_for_error(self, error_count: int) -> int:
        base = max(1, int(self.retry_base_seconds))
        cap = max(base, int(self.retry_max_seconds))
        exponent = min(max(error_count - 1, 0), 16)
        raw = min(cap, base * (2 ** exponent))

        jitter_fraction = min(max(float(self.retry_jitter_fraction), 0.0), 1.0)
        if jitter_fraction == 0:
            return int(raw)

        digest = hashlib.sha256(
            f"{self.adapter_id}:{error_count}".encode("utf-8")
        ).digest()
        unit = int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)
        multiplier = 1.0 + ((unit * 2.0) - 1.0) * jitter_fraction
        return max(1, min(cap, int(round(raw * multiplier))))

    def _resilience_snapshot(
        self,
        received_at: datetime,
        detail: str,
    ) -> AdapterSnapshot:
        if self._last_good_snapshot is not None:
            cached = self._last_good_snapshot.model_copy(deep=True)
            freshness = max(
                0,
                int((received_at - cached.provenance.observed_at).total_seconds()),
            )
            stale = freshness > self.stale_after_seconds
            health = AdapterHealth.STALE if stale else AdapterHealth.DEGRADED
            observed_at = cached.provenance.observed_at
            records = [dict(item) for item in cached.records]
            using_cached_records = True
        else:
            freshness = 0
            stale = True
            health = AdapterHealth.ERROR
            observed_at = received_at
            records = []
            using_cached_records = False

        return AdapterSnapshot(
            adapter_id=self.adapter_id,
            provenance=DataSourceProvenance(
                source_id=self.adapter_id,
                domain=self.domain,
                mode=DataSourceMode.LIVE,
                provider=self.provider,
                observed_at=observed_at,
                received_at=received_at,
                freshness_seconds=freshness,
                stale_after_seconds=self.stale_after_seconds,
                stale=stale,
                health=health,
                record_count=len(records),
                detail=detail,
                last_success_at=self._last_success_at,
                last_attempt_at=self._last_attempt_at,
                next_retry_at=self._next_retry_at,
                retry_delay_seconds=self._retry_delay_seconds,
                consecutive_errors=self._consecutive_errors,
                using_cached_records=using_cached_records,
            ),
            records=records,
        )

    def snapshot(self, now: datetime | None = None) -> AdapterSnapshot:
        received_at = (now or datetime.now(timezone.utc)).replace(microsecond=0)

        with self._lock:
            if (
                self._next_retry_at is not None
                and received_at < self._next_retry_at
            ):
                return self._resilience_snapshot(
                    received_at,
                    (
                        "Retry backoff active; next live attempt at "
                        f"{self._next_retry_at.isoformat()}."
                    ),
                )

            self._last_attempt_at = received_at

            try:
                payload = self.loader(self.url, self.timeout_seconds)
                observed_raw = payload.get("observed_at")
                records = payload.get("records")

                if not isinstance(observed_raw, str):
                    raise ValueError("Live adapter payload requires observed_at")
                if not isinstance(records, list):
                    raise ValueError("Live adapter payload requires records array")
                if not all(isinstance(item, dict) for item in records):
                    raise ValueError("Live adapter records must be JSON objects")

                observed_at = _parse_datetime(observed_raw)
                freshness = max(0, int((received_at - observed_at).total_seconds()))
                stale = freshness > self.stale_after_seconds
                health = AdapterHealth.STALE if stale else AdapterHealth.HEALTHY

                self._consecutive_errors = 0
                self._next_retry_at = None
                self._retry_delay_seconds = 0

                snapshot = AdapterSnapshot(
                    adapter_id=self.adapter_id,
                    provenance=DataSourceProvenance(
                        source_id=self.adapter_id,
                        domain=self.domain,
                        mode=DataSourceMode.LIVE,
                        provider=self.provider,
                        observed_at=observed_at,
                        received_at=received_at,
                        freshness_seconds=freshness,
                        stale_after_seconds=self.stale_after_seconds,
                        stale=stale,
                        health=health,
                        record_count=len(records),
                        detail=(
                            "Live HTTP JSON adapter."
                            if not stale
                            else "Live HTTP JSON adapter responded, but the observation is stale."
                        ),
                        last_success_at=self._last_success_at,
                        last_attempt_at=self._last_attempt_at,
                        next_retry_at=None,
                        retry_delay_seconds=0,
                        consecutive_errors=0,
                        using_cached_records=False,
                    ),
                    records=[dict(item) for item in records],
                )

                if health == AdapterHealth.HEALTHY:
                    self._last_success_at = received_at
                    snapshot.provenance.last_success_at = received_at
                    self._last_good_snapshot = snapshot.model_copy(deep=True)

                return snapshot

            except Exception as exc:
                self._consecutive_errors += 1
                self._retry_delay_seconds = self._retry_delay_for_error(
                    self._consecutive_errors
                )
                self._next_retry_at = received_at + timedelta(
                    seconds=self._retry_delay_seconds
                )
                return self._resilience_snapshot(
                    received_at,
                    (
                        f"Live adapter unavailable: {type(exc).__name__}; "
                        f"retry scheduled at {self._next_retry_at.isoformat()}."
                    ),
                )


_LIVE_ADAPTERS: dict[str, HttpJsonAdapter] = {}
_LIVE_ADAPTERS_LOCK = Lock()


def configured_live_adapters() -> dict[str, HttpJsonAdapter]:
    specs = (
        (
            "live-ais",
            DataDomain.AIS,
            "PORTFLOW_AIS_URL",
            "PORTFLOW_AIS_PROVIDER",
            "Configured AIS provider",
            120,
        ),
        (
            "live-weather",
            DataDomain.WEATHER_TIDE,
            "PORTFLOW_WEATHER_URL",
            "PORTFLOW_WEATHER_PROVIDER",
            "Configured weather/tide provider",
            300,
        ),
        (
            "live-berth-plan",
            DataDomain.BERTH_PLAN,
            "PORTFLOW_BERTH_PLAN_URL",
            "PORTFLOW_BERTH_PLAN_PROVIDER",
            "Configured berth-plan provider",
            600,
        ),
    )

    desired: dict[str, HttpJsonAdapter] = {}
    with _LIVE_ADAPTERS_LOCK:
        for adapter_id, domain, url_env, provider_env, provider_default, stale_after in specs:
            url = os.getenv(url_env, "").strip()
            if not url:
                continue

            provider = os.getenv(provider_env, provider_default).strip() or provider_default
            candidate = HttpJsonAdapter(
                adapter_id=adapter_id,
                domain=domain,
                provider=provider,
                url=url,
                stale_after_seconds=stale_after,
            )
            existing = _LIVE_ADAPTERS.get(adapter_id)
            desired[adapter_id] = (
                existing
                if existing is not None and existing.config_key() == candidate.config_key()
                else candidate
            )

        _LIVE_ADAPTERS.clear()
        _LIVE_ADAPTERS.update(desired)
        return dict(_LIVE_ADAPTERS)


def all_adapters() -> dict[str, ExternalDataAdapter]:
    combined: dict[str, ExternalDataAdapter] = dict(ADAPTERS)
    combined.update(configured_live_adapters())
    return combined


ADAPTERS: dict[str, RecordedFixtureAdapter] = {
    "recorded-ais": RecordedFixtureAdapter(
        adapter_id="recorded-ais",
        domain=DataDomain.AIS,
        provider="Shorefront recorded AIS fixture",
        stale_after_seconds=120,
        age_seconds=18,
        detail="Recorded fixture replay. Not a live AIS provider.",
        records=[
            {
                "vessel_id": "v-aurora",
                "lat": 51.982,
                "lon": 3.995,
                "speed_knots": 10.9,
                "heading_deg": 94.0,
                "eta_offset_minutes": 49,
            },
            {
                "vessel_id": "v-glory",
                "lat": 51.960,
                "lon": 4.061,
                "speed_knots": 5.8,
                "heading_deg": 106.0,
                "eta_offset_minutes": 19,
            },
        ],
    ),
    "recorded-weather": RecordedFixtureAdapter(
        adapter_id="recorded-weather",
        domain=DataDomain.WEATHER_TIDE,
        provider="Shorefront recorded metocean fixture",
        stale_after_seconds=300,
        age_seconds=42,
        detail="Recorded weather/tide fixture. Not a live metocean feed.",
        records=[
            {
                "wind_knots": 23.0,
                "gust_knots": 31.0,
                "visibility_km": 8.6,
                "wave_height_m": 1.5,
                "tide_m": 1.0,
            }
        ],
    ),
    "recorded-berth-plan": RecordedFixtureAdapter(
        adapter_id="recorded-berth-plan",
        domain=DataDomain.BERTH_PLAN,
        provider="Shorefront recorded berth-plan fixture",
        stale_after_seconds=600,
        age_seconds=75,
        detail="Recorded berth-plan fixture. Not a terminal operating system connection.",
        records=[
            {
                "port_call_id": "pc-nova",
                "berth_id": "b-07",
                "arrival_offset_minutes": 470,
                "departure_offset_minutes": 855,
            },
            {
                "port_call_id": "pc-aurora",
                "berth_id": "b-12",
                "arrival_offset_minutes": 51,
                "departure_offset_minutes": 535,
            },
        ],
    ),
    "stale-weather-fixture": RecordedFixtureAdapter(
        adapter_id="stale-weather-fixture",
        domain=DataDomain.WEATHER_TIDE,
        provider="Shorefront stale metocean fixture",
        stale_after_seconds=300,
        age_seconds=1200,
        detail="Intentionally stale fixture used to prove freshness handling.",
        records=[
            {
                "wind_knots": 17.0,
                "gust_knots": 21.0,
                "visibility_km": 10.2,
                "wave_height_m": 0.9,
                "tide_m": 0.6,
            }
        ],
    ),
}


def list_adapter_snapshots(now: datetime | None = None) -> list[AdapterSnapshot]:
    adapters = all_adapters()
    return [
        adapters[key].snapshot(now=now)
        for key in sorted(adapters)
    ]


def get_adapter_snapshot(
    adapter_id: str,
    now: datetime | None = None,
) -> AdapterSnapshot | None:
    adapter = all_adapters().get(adapter_id)
    if adapter is None:
        return None
    return adapter.snapshot(now=now)
