import logging
import os
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

MARKET_NO_PROXY_HOSTS = (
    "eastmoney.com",
    "push2.eastmoney.com",
    "push2his.eastmoney.com",
    "88.push2.eastmoney.com",
    "17.push2.eastmoney.com",
    "datacenter-web.eastmoney.com",
    "chinamoney.com.cn",
    "cninfo.com.cn",
    "finance.sina.com.cn",
    "sina.com.cn",
)

RETRIABLE_MARKERS = (
    "ProxyError",
    "RemoteDisconnected",
    "ConnectionError",
    "Timeout",
    "timed out",
    "Connection reset",
    "Connection aborted",
    "Max retries exceeded",
    "eastmoney.com",
    "SSLError",
    "Read timed out",
)

_network_env_applied = False


def is_retriable_market_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in RETRIABLE_MARKERS)


def ensure_market_network_env(*, no_proxy: bool = True) -> None:
    global _network_env_applied
    if _network_env_applied or not no_proxy:
        return
    hosts = ",".join(MARKET_NO_PROXY_HOSTS)
    for key in ("NO_PROXY", "no_proxy"):
        current = (os.environ.get(key) or "").strip()
        parts = [part.strip() for part in current.split(",") if part.strip()]
        for host in MARKET_NO_PROXY_HOSTS:
            if host not in parts:
                parts.append(host)
        os.environ[key] = ",".join(parts) if parts else hosts
    _network_env_applied = True
    logger.debug("market network env applied NO_PROXY hosts=%s", hosts)


def retry_call(
    func: Callable[[], T],
    *,
    retries: int = 3,
    delay: float = 1.0,
    retriable_only: bool = False,
) -> T:
    last_exc: Exception | None = None
    attempts = max(1, int(retries))
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if retriable_only and not is_retriable_market_error(exc):
                raise
            if attempt < attempts - 1:
                sleep_sec = delay * (attempt + 1)
                logger.warning(
                    "market retry %s/%s after %s: %s",
                    attempt + 1,
                    attempts,
                    sleep_sec,
                    str(exc)[:160],
                )
                time.sleep(sleep_sec)
    assert last_exc is not None
    raise last_exc


def get_retry_settings() -> tuple[int, float, bool]:
    try:
        from app.config.settings import settings

        return (
            max(1, int(settings.market_retry_count)),
            max(0.2, float(settings.market_retry_delay_sec)),
            bool(settings.market_retry_retriable_only),
        )
    except Exception:
        return 3, 1.0, False


def market_retry_call(func: Callable[[], T]) -> T:
    retries, delay, retriable_only = get_retry_settings()
    return retry_call(func, retries=retries, delay=delay, retriable_only=retriable_only)
