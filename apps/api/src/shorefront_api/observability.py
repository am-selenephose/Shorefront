from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
from threading import Lock
from time import perf_counter
from typing import Callable

from fastapi import Request


logger = logging.getLogger("uvicorn.error")


def _escape_label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._http: dict[tuple[str, str, int], int] = defaultdict(int)
        self._counters: dict[str, int] = defaultdict(int)

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def inc_http(self, method: str, route: str, status: int) -> None:
        with self._lock:
            self._http[(method, route, status)] += 1

    def counter(self, name: str) -> int:
        with self._lock:
            return int(self._counters.get(name, 0))

    def render(
        self,
        *,
        runtime_ready: bool,
        schema_compatible: bool,
        authorization_configured: bool,
        harbor_metrics: dict[str, int | float] | None,
    ) -> str:
        with self._lock:
            http_rows = sorted(self._http.items())
            counters = dict(self._counters)

        lines = [
            "# HELP portflow_runtime_ready Whether the application runtime is initialized.",
            "# TYPE portflow_runtime_ready gauge",
            f"portflow_runtime_ready {1 if runtime_ready else 0}",
            "# HELP portflow_schema_compatible Whether persistence schema matches this build.",
            "# TYPE portflow_schema_compatible gauge",
            f"portflow_schema_compatible {1 if schema_compatible else 0}",
            "# HELP portflow_authorization_configured Whether operator approvers are configured.",
            "# TYPE portflow_authorization_configured gauge",
            f"portflow_authorization_configured {1 if authorization_configured else 0}",
        ]

        dynamic = harbor_metrics or {}
        for metric_name, source_key in (
            ("portflow_active_incidents", "active_incidents"),
            ("portflow_blocked_services", "blocked_services"),
            ("portflow_stale_data_sources", "stale_data_sources"),
        ):
            lines.extend([
                f"# TYPE {metric_name} gauge",
                f"{metric_name} {float(dynamic.get(source_key, 0)):g}",
            ])

        counter_names = (
            "portflow_calibration_updates_total",
            "portflow_adapter_ingests_total",
            "portflow_recovery_approvals_total",
            "portflow_recovery_contingencies_total",
            "portflow_replay_acks_total",
            "portflow_scenario_runs_total",
            "portflow_vessel_events_total",
        )
        for name in counter_names:
            lines.extend([
                f"# TYPE {name} counter",
                f"{name} {int(counters.get(name, 0))}",
            ])

        lines.extend([
            "# HELP portflow_http_requests_total HTTP requests by method, route template, and status.",
            "# TYPE portflow_http_requests_total counter",
        ])
        for (method, route, status), count in http_rows:
            lines.append(
                "portflow_http_requests_total"
                f'{{method="{_escape_label(method)}",'
                f'route="{_escape_label(route)}",'
                f'status="{status}"}} {count}'
            )

        return "\n".join(lines) + "\n"

    def render_operational(
        self,
        *,
        runtime_ready: bool,
        records_total: int,
        users_total: int,
        active_sessions: int,
        open_conflicts: int,
    ) -> str:
        with self._lock:
            http_rows = sorted(self._http.items())

        lines = [
            "# HELP shorefront_runtime_ready Whether the operational runtime is ready.",
            "# TYPE shorefront_runtime_ready gauge",
            f"shorefront_runtime_ready {1 if runtime_ready else 0}",
            "# HELP shorefront_records_total Current record-version rows stored by this installation.",
            "# TYPE shorefront_records_total gauge",
            f"shorefront_records_total {int(records_total)}",
            "# HELP shorefront_users_total Current user accounts stored by this installation.",
            "# TYPE shorefront_users_total gauge",
            f"shorefront_users_total {int(users_total)}",
            "# HELP shorefront_active_sessions Current non-expired sessions stored by this installation.",
            "# TYPE shorefront_active_sessions gauge",
            f"shorefront_active_sessions {int(active_sessions)}",
            "# HELP shorefront_open_reconciliation_conflicts Current unresolved factual disagreements.",
            "# TYPE shorefront_open_reconciliation_conflicts gauge",
            f"shorefront_open_reconciliation_conflicts {int(open_conflicts)}",
            "# HELP shorefront_http_requests_total HTTP requests by method, route template, and status.",
            "# TYPE shorefront_http_requests_total counter",
        ]
        for (method, route, status), count in http_rows:
            lines.append(
                "shorefront_http_requests_total"
                f'{{method="{_escape_label(method)}",'
                f'route="{_escape_label(route)}",'
                f'status="{status}"}} {count}'
            )
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


async def observe_http(request: Request, call_next: Callable):
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        metrics.inc_http(request.method, route_path, status)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "http_request",
            "method": request.method,
            "route": route_path,
            "status": status,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
        }
        logger.info(json.dumps(record, sort_keys=True, separators=(",", ":")))
