import asyncio
import re
import threading
import time
from datetime import datetime
from functools import partial
from typing import Any, Callable, TypeVar

from .schemes import INDEX_WIND_CODES

T = TypeVar("T")

_SYMBOL_RE = re.compile(r"^(?:(?P<prefix>sh|sz|bj))?(?P<code>\d{4,6})(?:\.(?P<suffix>SH|SZ|BJ|HK))?$", re.I)
_HK_SYMBOL_RE = re.compile(r"^(?:(?P<prefix>hk))?(?P<code>\d{4,5})(?:\.HK)?$", re.I)
_CACHE_LOCK = threading.RLock()


def run_sync(func: Callable[..., T], *args: Any, **kwargs: Any):
    return asyncio.to_thread(partial(func, *args, **kwargs))


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def normalize_date(value: str | None, *, default: str | None = None) -> str:
    if not value:
        return default or today_str()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def to_ak_date(value: str | None) -> str:
    return normalize_date(value).replace("-", "")


def parse_symbol(symbol: str, market: str | None = None) -> tuple[str, str]:
    raw = (symbol or "").strip()
    if not raw:
        raise ValueError("symbol is required")
    market_key = (market or "").strip().upper()
    hk_match = _HK_SYMBOL_RE.match(raw)
    if market_key == "HK" or (hk_match and not raw.upper().endswith(("SH", "SZ", "BJ"))):
        code = hk_match.group("code") if hk_match else raw.replace(".HK", "").replace("hk", "")
        return code.zfill(5), "HK"
    match = _SYMBOL_RE.match(raw)
    if not match:
        raise ValueError(f"invalid symbol: {symbol}")
    code = match.group("code")
    suffix = (match.group("suffix") or "").upper()
    prefix = (match.group("prefix") or "").lower()
    if suffix == "HK" or prefix == "hk":
        return code.zfill(5), "HK"
    if suffix in {"SH", "SZ", "BJ"} or prefix in {"sh", "sz", "bj"}:
        return code, "CN_A"
    if code.startswith(("6", "9", "0", "3", "4", "8")):
        return code, "CN_A"
    return code, market_key or "CN_A"


def to_ts_code(code: str) -> str:
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def to_wind_code(symbol: str, market: str | None = None) -> tuple[str, str]:
    code, market_key = parse_symbol(symbol, market)
    if market_key == "HK":
        trimmed = code.lstrip("0") or "0"
        return f"{trimmed}.HK", market_key
    if symbol.upper() in {"HSI", "HSI.HK", "HSI.HI"} or code == "HSI":
        return "HSI.HI", "HK"
    key = symbol.strip()
    if key in INDEX_WIND_CODES:
        return INDEX_WIND_CODES[key], "CN_A" if not key.upper().startswith("HSI") else "HK"
    return to_ts_code(code), market_key


def cn_exchange_prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("0", "3")):
        return "sz"
    if code.startswith(("4", "8")):
        return "bj"
    return "sz"


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            text = value.strip().replace(",", "").replace("%", "")
            if text in {"", "-", "--", "nan", "None"}:
                return None
            return float(text)
        num = float(value)
        if num != num:
            return None
        return num
    except (TypeError, ValueError):
        return None


def pick_column(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def percentile_of(value: float, series: list[float]) -> float | None:
    if not series:
        return None
    return round(float(sum(1 for item in series if item <= value) / len(series)) * 100, 2)


def retry_call(func: Callable[[], T], *, retries: int = 3, delay: float = 1.0) -> T:
    from .resilience import market_retry_call

    if retries == 3 and delay == 1.0:
        return market_retry_call(func)
    from .resilience import retry_call as _retry_call

    return _retry_call(func, retries=retries, delay=delay)


class TtlCache:
    def __init__(self, ttl_sec: int = 300) -> None:
        self._ttl = ttl_sec
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        with _CACHE_LOCK:
            item = self._store.get(key)
            if not item:
                return None
            ts, value = item
            if time.time() - ts > self._ttl:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> Any:
        with _CACHE_LOCK:
            self._store[key] = (time.time(), value)
            return value
