"""Explicit opt-in NOAA CO-OPS read-only observations, never port authority."""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
import json
import re
from threading import Lock
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

URL = 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter'
LIMITATIONS = [
    'Station association is configured by the operator, not independently verified against port geography.',
    'Preliminary NOAA observations may be revised or unavailable.',
    'This observation is not water-depth clearance, a traffic prediction, or authority to move a vessel.',
]


def _result(station: str, status: str, now: datetime, observation=None) -> dict:
    return {
        'provider': 'NOAA CO-OPS',
        'station_id': station,
        'status': status,
        'observation': observation,
        'source_url': URL,
        'retrieved_at': now.isoformat(),
        'scope': 'operator_configured_station',
        'physical_execution_authorized': False,
        'limitations': LIMITATIONS,
    }


class NoaaCoopsClient:
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
        opener: Callable | None = None,
    ):
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._opener = opener or urlopen
        self._cache: dict[str, tuple[datetime, dict]] = {}
        self._lock = Lock()

    def read(self, station: str) -> dict:
        now = self._now()
        if not re.fullmatch(r'[0-9]{7}', station):
            return _result(station, 'unavailable', now)
        with self._lock:
            cached = self._cache.get(station)
            if cached and (now - cached[0]).total_seconds() < 60:
                return dict(cached[1])

        params = urlencode({
            'date': 'latest', 'station': station, 'product': 'water_level',
            'datum': 'MLLW', 'units': 'metric', 'time_zone': 'gmt',
            'application': 'Shorefront', 'format': 'json',
        })
        try:
            with self._opener(URL+'?'+params, timeout=4) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('NOAA response too large')
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError('Unexpected NOAA document shape')
            metadata = body.get('metadata')
            samples = body.get('data')
            if not isinstance(metadata, dict) or str(metadata.get('id')) != station:
                raise ValueError('Unexpected station identity')
            if not isinstance(samples, list) or len(samples) != 1:
                raise ValueError('No single latest observation')
            row = samples[0]
            if not isinstance(row, dict):
                raise ValueError('Unexpected NOAA measurement shape')
            measurement = float(row['v'])
            if not isfinite(measurement):
                raise ValueError('Invalid water level')
            observed = datetime.strptime(row['t'], '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
            age = (now-observed).total_seconds()
            if age < -300:
                raise ValueError('Observation timestamp lies in the future')
            freshness = 'current' if age <= 1800 else 'stale'
            observation = {
                'level_m': measurement, 'observed_at': observed.isoformat(),
                'datum': 'MLLW', 'units': 'm',
                'quality': 'preliminary' if str(row.get('q', '')).lower() == 'p' else 'unverified',
            }
            result = _result(station, freshness, now, observation)
        except (OSError, HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            result = _result(station, 'unavailable', now)

        with self._lock:
            self._cache[station] = (now, result)
        return dict(result)
