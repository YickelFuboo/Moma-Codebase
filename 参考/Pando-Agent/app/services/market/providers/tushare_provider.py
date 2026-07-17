import logging
from datetime import datetime, timedelta
from typing import Any
import pandas as pd
from ..schemes import INDEX_TS_CODES, resolve_index
from ..utils import parse_symbol, percentile_of, retry_call, safe_float, to_ts_code

logger = logging.getLogger(__name__)


class TushareMarketProvider:
    name = "tushare"
    source = "tushare_pro"

    def __init__(self, token: str) -> None:
        import tushare as ts
        self._pro = ts.pro_api(token)

    def get_realtime_quote(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        if market_key == "HK":
            raise ValueError("tushare realtime for HK not implemented")
        ts_code = to_ts_code(code)
        df = retry_call(lambda: self._pro.daily_basic(ts_code=ts_code, fields="ts_code,trade_date,close,turnover_rate,pe_ttm,pb,total_mv,circ_mv"))
        if df is None or df.empty:
            raise ValueError(f"symbol not found: {symbol}")
        row = df.sort_values("trade_date").iloc[-1]
        return {
            "symbol": code,
            "market": market_key,
            "price": safe_float(row.get("close")),
            "turnover_rate": safe_float(row.get("turnover_rate")),
            "pe_ttm": safe_float(row.get("pe_ttm")),
            "pb": safe_float(row.get("pb")),
            "market_cap": safe_float(row.get("total_mv")),
            "float_market_cap": safe_float(row.get("circ_mv")),
            "delayed": True,
            "source": self.source,
            "provider": self.name,
            "as_of_date": str(row.get("trade_date"))[:10],
        }

    def get_stock_snapshot(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        snapshot = self.get_realtime_quote(symbol, market)
        fundamentals = self.get_stock_fundamentals(symbol, years=1, market=market)
        latest = fundamentals.get("records", [{}])[-1] if fundamentals.get("records") else {}
        snapshot.update({k: latest.get(k) for k in ("roe", "gross_margin", "debt_ratio", "net_profit_yoy", "revenue_yoy")})
        snapshot["financial_report_date"] = latest.get("report_date")
        return snapshot

    def get_stock_fundamentals(self, symbol: str, *, years: int = 5, market: str | None = None) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        if market_key != "CN_A":
            raise ValueError("tushare fundamentals currently supports CN_A only")
        ts_code = to_ts_code(code)
        df = retry_call(
            lambda: self._pro.fina_indicator(
                ts_code=ts_code,
                fields=(
                    "ts_code,end_date,roe,grossprofit_margin,debt_to_assets,netprofit_yoy,or_yoy,"
                    "ocf_to_profit,ebitda,interestdebt"
                ),
            )
        )
        if df is None or df.empty:
            raise ValueError(f"fundamentals unavailable: {symbol}")
        df = df.sort_values("end_date")
        records = []
        for _, row in df.iterrows():
            records.append(
                {
                    "report_date": str(row.get("end_date"))[:10],
                    "roe": safe_float(row.get("roe")),
                    "gross_margin": safe_float(row.get("grossprofit_margin")),
                    "debt_ratio": safe_float(row.get("debt_to_assets")),
                    "net_profit_yoy": safe_float(row.get("netprofit_yoy")),
                    "revenue_yoy": safe_float(row.get("or_yoy")),
                    "ocf_to_net_income": safe_float(row.get("ocf_to_profit")),
                    "ebitda": safe_float(row.get("ebitda")),
                    "interest_bearing_debt": safe_float(row.get("interestdebt")),
                }
            )
        if years > 0:
            records = records[-years:]
        return {
            "symbol": code,
            "market": market_key,
            "years": years,
            "records": records,
            "source": self.source,
            "provider": self.name,
            "as_of_date": records[-1]["report_date"] if records else datetime.now().strftime("%Y-%m-%d"),
        }

    def get_stock_valuation(self, symbol: str, *, window_years: int = 5, market: str | None = None) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        ts_code = to_ts_code(code)
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=365 * max(window_years, 1))).strftime("%Y%m%d")
        df = retry_call(
            lambda: self._pro.daily_basic(
                ts_code=ts_code,
                start_date=start,
                end_date=end,
                fields="trade_date,pe_ttm,pb,total_mv,dv_ratio",
            )
        )
        if df is None or df.empty:
            raise ValueError(f"valuation unavailable: {symbol}")
        df = df.sort_values("trade_date")
        latest = df.iloc[-1]
        pe_series = pd.to_numeric(df["pe_ttm"], errors="coerce").dropna().tolist()
        pe_ttm = safe_float(latest.get("pe_ttm"))
        fin = self.get_stock_fundamentals(symbol, years=1, market=market)
        growth = fin["records"][-1].get("net_profit_yoy") if fin.get("records") else None
        peg = round(pe_ttm / growth, 4) if pe_ttm and growth and growth > 0 else None
        return {
            "symbol": code,
            "market": market_key,
            "pe_ttm": pe_ttm,
            "pb": safe_float(latest.get("pb")),
            "pe_percentile": percentile_of(pe_ttm, pe_series) if pe_ttm else None,
            "percentile_window_years": window_years,
            "dividend_yield_pct": safe_float(latest.get("dv_ratio")),
            "peg": peg,
            "profit_growth_yoy_pct": growth,
            "source": self.source,
            "provider": self.name,
            "as_of_date": str(latest.get("trade_date"))[:10],
        }

    def get_bars(self, symbol: str, *, freq: str = "1d", start: str | None = None, end: str | None = None, adjust: str = "qfq", market: str | None = None, limit: int | None = None) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for bars")

    def screen_stocks(self, *, market: str = "CN_A", filters: dict[str, Any] | None = None, wencai_query: str | None = None, sort_by: str = "amount", limit: int = 50) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for screen_stocks")

    def get_index_valuation(self, index: str, *, window_years: int = 5) -> dict[str, Any]:
        ts_code = INDEX_TS_CODES.get(resolve_index(index), resolve_index(index))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=365 * max(window_years, 1))).strftime("%Y%m%d")
        df = retry_call(
            lambda: self._pro.index_dailybasic(
                ts_code=ts_code,
                start_date=start,
                end_date=end,
                fields="trade_date,pe_ttm,pb,total_mv",
            )
        )
        if df is None or df.empty:
            raise ValueError(f"index valuation unavailable: {index}")
        df = df.sort_values("trade_date")
        pe_series = pd.to_numeric(df["pe_ttm"], errors="coerce").dropna().tolist()
        latest = df.iloc[-1]
        pe_ttm = safe_float(latest.get("pe_ttm"))
        return {
            "index": index,
            "index_name": ts_code,
            "pe_ttm": pe_ttm,
            "pe_percentile": percentile_of(pe_ttm, pe_series) if pe_ttm else None,
            "percentile_window_years": window_years,
            "sample_size": len(pe_series),
            "latest_date": str(latest.get("trade_date"))[:10],
            "source": self.source,
            "provider": self.name,
        }

    def get_macro_rate(self, indicator: str = "cn_10y") -> dict[str, Any]:
        df = retry_call(lambda: self._pro.yc_cb(ts_code="1001.CB", fields="trade_date,y10"))
        if df is None or df.empty:
            raise ValueError("macro rate unavailable")
        latest = df.sort_values("trade_date").iloc[-1]
        return {
            "indicator": indicator,
            "value_pct": safe_float(latest.get("y10")),
            "date": str(latest.get("trade_date"))[:10],
            "source": self.source,
            "provider": self.name,
        }

    def get_etf_snapshot(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for ETF snapshot")

    def search_announcements(self, symbol: str, *, limit: int = 10) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for announcements")

    def get_market_sentiment(self, *, days: int = 5, window_years: int = 5) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for market sentiment")

    def get_market_liquidity(self, *, window_years: int = 1, index: str = "000985") -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for market liquidity")

    def get_cross_market_indicators(self) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for cross market indicators")

    def get_market_volatility(self, *, index: str = "000300", days: int = 20) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for market volatility")
