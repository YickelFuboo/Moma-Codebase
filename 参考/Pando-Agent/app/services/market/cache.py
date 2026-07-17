from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from .utils import TtlCache

T = TypeVar("T")

_DATA_CACHE: TtlCache | None = None


def market_cache_ttl(*, minimum: int = 30) -> int:
    try:
        from app.config.settings import settings

        return max(minimum, int(settings.market_cache_ttl_sec))
    except Exception:
        return 300


def get_data_cache() -> TtlCache:
    global _DATA_CACHE
    if _DATA_CACHE is None:
        _DATA_CACHE = TtlCache(ttl_sec=market_cache_ttl())
    return _DATA_CACHE


def reset_data_cache() -> None:
    global _DATA_CACHE
    _DATA_CACHE = None


def cached_dict(key: str, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    cache = get_data_cache()
    hit = cache.get(key)
    if hit is not None:
        return dict(hit)
    value = dict(loader())
    cache.set(key, value)
    return dict(value)


def provider_cached(key_builder: Callable[..., str]) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def decorator(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            key = key_builder(*args, **kwargs)
            return cached_dict(key, lambda: func(*args, **kwargs))

        return wrapper

    return decorator
