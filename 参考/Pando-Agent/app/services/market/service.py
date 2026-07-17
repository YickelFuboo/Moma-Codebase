import json
import logging
import time
from typing import Any, Callable
from app.config.settings import settings
from .metrics import record_health_check, record_provider_call
from .providers.akshare_provider import AkshareMarketProvider
from .resilience import ensure_market_network_env
from .technical import compute_indicators
from .utils import run_sync, today_str

logger = logging.getLogger(__name__)
_service: "MarketDataService | None" = None


class MarketDataService:
    """Market 数据公共服务：Provider 链 + 能力路由。

    数据诚信：只返回可追溯原始序列；无法取得官方/同源数据时抛错或 ``available: false``，
    禁止用其它指标推算冒充。缺口由 Agent 经 web_fetch 官方源补齐。
    """

    def __init__(self) -> None:
        ensure_market_network_env(no_proxy=settings.market_no_proxy)
        self._akshare = AkshareMarketProvider()
        self._wind = None
        self._choice = None
        self._tushare = None
        self._init_optional_providers()

    def _init_optional_providers(self) -> None:
        if settings.wind_enabled:
            try:
                from .providers.wind_provider import WindMarketProvider
                self._wind = WindMarketProvider()
            except Exception as exc:
                logger.warning("wind provider disabled: %s", exc)
        username = (settings.choice_username or "").strip()
        password = (settings.choice_password or "").strip()
        if username and password:
            try:
                from .providers.choice_provider import ChoiceMarketProvider
                self._choice = ChoiceMarketProvider(
                    username,
                    password,
                    (settings.choice_activate_code or "").strip(),
                )
            except Exception as exc:
                logger.warning("choice provider disabled: %s", exc)
        token = (settings.tushare_token or "").strip()
        if token:
            try:
                from .providers.tushare_provider import TushareMarketProvider
                self._tushare = TushareMarketProvider(token)
            except Exception as exc:
                logger.warning("tushare provider disabled: %s", exc)

    def _providers(self) -> list[Any]:
        mode = (settings.market_data_provider or "auto").strip().lower()
        fallback = [self._akshare]
        if mode == "akshare":
            return fallback
        if mode == "tushare":
            return ([self._tushare] if self._tushare else []) + fallback
        if mode == "wind":
            return ([self._wind] if self._wind else []) + fallback
        if mode == "choice":
            return ([self._choice] if self._choice else []) + fallback
        chain: list[Any] = []
        if self._wind:
            chain.append(self._wind)
        if self._choice:
            chain.append(self._choice)
        if self._tushare:
            chain.append(self._tushare)
        chain.extend(fallback)
        return chain

    def list_providers(self) -> list[str]:
        return [p.name for p in self._providers()]

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        errors: list[str] = []
        started = time.perf_counter()
        used_provider = "none"
        for provider in self._providers():
            func: Callable[..., Any] | None = getattr(provider, method, None)
            if func is None:
                continue
            used_provider = provider.name
            try:
                result = func(*args, **kwargs)
                if settings.market_metrics_enabled:
                    record_provider_call(
                        method,
                        provider.name,
                        ok=True,
                        duration_ms=(time.perf_counter() - started) * 1000,
                    )
                return result
            except NotImplementedError:
                continue
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                logger.warning("market provider %s.%s failed: %s", provider.name, method, exc)
        if settings.market_metrics_enabled:
            record_provider_call(
                method,
                used_provider,
                ok=False,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        raise RuntimeError(f"{method} failed: {'; '.join(errors) or 'no provider available'}")

    async def get_realtime_quote(self, symbol: str, *, market: str | None = None) -> dict[str, Any]:
        return await run_sync(self._call, "get_realtime_quote", symbol, market=market)

    async def get_stock_snapshot(self, symbol: str, *, market: str | None = None) -> dict[str, Any]:
        return await run_sync(self._call, "get_stock_snapshot", symbol, market=market)

    async def get_stock_fundamentals(self, symbol: str, *, years: int = 5, market: str | None = None) -> dict[str, Any]:
        return await run_sync(self._call, "get_stock_fundamentals", symbol, years=years, market=market)

    async def get_stock_valuation(self, symbol: str, *, window_years: int = 5, market: str | None = None) -> dict[str, Any]:
        return await run_sync(self._call, "get_stock_valuation", symbol, window_years=window_years, market=market)

    async def get_bars(
        self,
        symbol: str,
        *,
        freq: str = "1d",
        start: str | None = None,
        end: str | None = None,
        adjust: str = "qfq",
        market: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await run_sync(
            self._call,
            "get_bars",
            symbol,
            freq=freq,
            start=start,
            end=end,
            adjust=adjust,
            market=market,
            limit=limit,
        )

    async def screen_stocks(
        self,
        *,
        market: str = "CN_A",
        filters: dict[str, Any] | None = None,
        wencai_query: str | None = None,
        sort_by: str = "amount",
        limit: int = 50,
    ) -> dict[str, Any]:
        return await run_sync(
            self._call,
            "screen_stocks",
            market=market,
            filters=filters,
            wencai_query=wencai_query,
            sort_by=sort_by,
            limit=limit,
        )

    async def get_index_valuation(self, index: str, *, window_years: int = 5) -> dict[str, Any]:
        return await run_sync(self._call, "get_index_valuation", index, window_years=window_years)

    async def get_macro_rate(self, indicator: str = "cn_10y") -> dict[str, Any]:
        return await run_sync(self._call, "get_macro_rate", indicator)

    async def get_cash_market_snapshot(self, *, top_n: int = 10) -> dict[str, Any]:
        return await run_sync(self._call, "get_cash_market_snapshot", top_n=top_n)

    async def get_etf_snapshot(self, symbol: str) -> dict[str, Any]:
        return await run_sync(self._call, "get_etf_snapshot", symbol)

    async def screen_etfs(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort_by: str = "amount",
        limit: int = 50,
    ) -> dict[str, Any]:
        return await run_sync(
            self._call,
            "screen_etfs",
            filters=filters,
            sort_by=sort_by,
            limit=limit,
        )

    async def get_chip_distribution(self, symbol: str, *, market: str | None = None) -> dict[str, Any]:
        return await run_sync(self._call, "get_chip_distribution", symbol, market=market)

    async def search_announcements(
        self, symbol: str, *, limit: int = 10, market: str | None = None
    ) -> dict[str, Any]:
        return await run_sync(self._call, "search_announcements", symbol, limit=limit, market=market)

    async def get_market_sentiment(self, *, days: int = 5, window_years: int = 5) -> dict[str, Any]:
        return await run_sync(self._call, "get_market_sentiment", days=days, window_years=window_years)

    async def get_market_liquidity(self, *, window_years: int = 1, index: str = "000985") -> dict[str, Any]:
        return await run_sync(self._call, "get_market_liquidity", window_years=window_years, index=index)

    async def get_cross_market_indicators(self) -> dict[str, Any]:
        return await run_sync(self._call, "get_cross_market_indicators")

    async def get_etf_fund_flow(self, *, weeks: int = 4) -> dict[str, Any]:
        return await run_sync(self._call, "get_etf_fund_flow", weeks=weeks)

    async def get_sector_liquidity(
        self,
        sector: str,
        *,
        window_years: int = 5,
        consecutive_days: int = 5,
        high_percentile: float = 90.0,
    ) -> dict[str, Any]:
        return await run_sync(
            self._call,
            "get_sector_liquidity",
            sector,
            window_years=window_years,
            consecutive_days=consecutive_days,
            high_percentile=high_percentile,
        )

    async def get_market_volatility(self, *, index: str = "000300", days: int = 20) -> dict[str, Any]:
        return await run_sync(self._call, "get_market_volatility", index=index, days=days)

    async def get_overseas_market_snapshot(
        self,
        *,
        symbols: list[str] | None = None,
        window_years: int = 10,
        include_technicals: bool = True,
    ) -> dict[str, Any]:
        return await run_sync(
            self._call,
            "get_overseas_market_snapshot",
            symbols=symbols,
            window_years=window_years,
            include_technicals=include_technicals,
        )

    def health_check(self) -> dict[str, Any]:
        probes: list[dict[str, Any]] = []
        probe_specs = (
            ("macro_rate", lambda: self._call("get_macro_rate", "cn_10y")),
            ("index_valuation", lambda: self._call("get_index_valuation", "000300", window_years=5)),
        )
        for name, func in probe_specs:
            item: dict[str, Any] = {"probe": name, "ok": False}
            try:
                result = func()
                item["ok"] = True
                item["provider"] = result.get("provider")
                item["as_of_date"] = result.get("date") or result.get("latest_date") or result.get("as_of_date")
            except Exception as exc:
                item["error"] = str(exc)[:240]
                item["retriable"] = self._is_retriable(str(exc))
            probes.append(item)
        ok_count = sum(1 for probe in probes if probe.get("ok"))
        if ok_count == len(probes):
            status = "healthy"
        elif ok_count > 0:
            status = "degraded"
        else:
            status = "unhealthy"
        payload = {
            "status": status,
            "providers": self.list_providers(),
            "provider_mode": (settings.market_data_provider or "auto").strip().lower(),
            "probes": probes,
            "config": {
                "retry_count": settings.market_retry_count,
                "cache_ttl_sec": settings.market_cache_ttl_sec,
                "no_proxy": settings.market_no_proxy,
            },
            "as_of_date": today_str(),
        }
        if settings.market_metrics_enabled:
            record_health_check(payload)
        return payload

    @staticmethod
    def _is_retriable(message: str) -> bool:
        from .resilience import is_retriable_market_error

        return is_retriable_market_error(RuntimeError(message))

    async def check_health(self) -> dict[str, Any]:
        return await run_sync(self.health_check)

    async def calc_technical(
        self,
        symbol: str,
        *,
        freq: str = "1d",
        indicators: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        adjust: str = "qfq",
        market: str | None = None,
        bar_limit: int = 260,
    ) -> dict[str, Any]:
        bars_payload = await self.get_bars(
            symbol,
            freq="1d" if freq in {"1w", "1m"} else freq,
            start=start,
            end=end,
            adjust=adjust,
            market=market,
            limit=bar_limit,
        )
        indicator_list = indicators or ["ma60", "ma120", "volume_ratio_20d", "box_pattern"]
        values = compute_indicators(bars_payload.get("bars") or [], indicators=indicator_list, freq=freq)
        return {
            "symbol": bars_payload.get("symbol"),
            "market": bars_payload.get("market"),
            "freq": freq,
            "adjust": adjust,
            "indicators": indicator_list,
            "values": values,
            "source": bars_payload.get("source"),
            "provider": bars_payload.get("provider"),
            "as_of_date": values.get("latest_date") or bars_payload.get("as_of_date"),
        }


def get_market_service() -> MarketDataService:
    global _service
    if _service is None:
        _service = MarketDataService()
    return _service


def market_json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
