import threading
import time
from collections import defaultdict
from typing import Any

_lock = threading.Lock()
_request_total: dict[tuple[str, str, str], int] = defaultdict(int)
_request_duration_ms: dict[tuple[str, str], float] = defaultdict(float)
_health_checks_total = 0
_health_checks_failed = 0
_last_health: dict[str, Any] | None = None
_last_health_at = 0.0

_STATUS_CODES = {"unhealthy": 0, "degraded": 1, "healthy": 2, "unknown": -1}


def record_provider_call(
    method: str,
    provider: str,
    *,
    ok: bool,
    duration_ms: float,
) -> None:
    status = "success" if ok else "error"
    key = (method, provider, status)
    with _lock:
        _request_total[key] += 1
        _request_duration_ms[(method, provider)] += max(0.0, duration_ms)


def record_health_check(payload: dict[str, Any]) -> None:
    global _health_checks_total, _health_checks_failed, _last_health, _last_health_at
    status = str(payload.get("status") or "unknown")
    with _lock:
        _health_checks_total += 1
        if status == "unhealthy":
            _health_checks_failed += 1
        _last_health = payload
        _last_health_at = time.time()


def get_last_health() -> dict[str, Any] | None:
    with _lock:
        return None if _last_health is None else dict(_last_health)


def render_prometheus() -> str:
    lines = [
        "# HELP market_health_status Market service health status (-1 unknown, 0 unhealthy, 1 degraded, 2 healthy).",
        "# TYPE market_health_status gauge",
    ]
    with _lock:
        status = str((_last_health or {}).get("status") or "unknown")
        lines.append(f"market_health_status {_STATUS_CODES.get(status, -1)}")
        lines.extend(
            [
                "# HELP market_health_checks_total Total market health probe runs.",
                "# TYPE market_health_checks_total counter",
                f"market_health_checks_total {_health_checks_total}",
                "# HELP market_health_checks_failed_total Total unhealthy market health probe runs.",
                "# TYPE market_health_checks_failed_total counter",
                f"market_health_checks_failed_total {_health_checks_failed}",
            ]
        )
        if _last_health_at:
            lines.extend(
                [
                    "# HELP market_health_last_check_timestamp_seconds Unix timestamp of last market health check.",
                    "# TYPE market_health_last_check_timestamp_seconds gauge",
                    f"market_health_last_check_timestamp_seconds {_last_health_at:.3f}",
                ]
            )
        lines.extend(
            [
                "# HELP market_provider_requests_total Market provider calls by method/provider/status.",
                "# TYPE market_provider_requests_total counter",
            ]
        )
        for (method, provider, status), count in sorted(_request_total.items()):
            lines.append(
                f'market_provider_requests_total{{method="{method}",provider="{provider}",status="{status}"}} {count}'
            )
        lines.extend(
            [
                "# HELP market_provider_request_duration_ms_sum Accumulated provider call duration in milliseconds.",
                "# TYPE market_provider_request_duration_ms_sum counter",
            ]
        )
        for (method, provider), duration in sorted(_request_duration_ms.items()):
            lines.append(
                f'market_provider_request_duration_ms_sum{{method="{method}",provider="{provider}"}} {duration:.3f}'
            )
    return "\n".join(lines) + "\n"
