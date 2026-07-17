import logging
import time
from datetime import datetime, timedelta
from typing import Any
import pandas as pd
from ..schemes import GLOBAL_INDEX_EM_NAMES, INDEX_ALIASES, global_index_em_name, is_global_index, is_hsi_index, resolve_index
from ..fundamentals_extra import compute_dividend_ttm_yield, enrich_fundamentals_payload
from ..overseas_eps import build_eps_growth_outlook
from ..overseas_snapshot import (
    DEFAULT_QDII_SYMBOLS,
    OVERSEAS_INDEX_CODES,
    build_overseas_relative_value,
    compute_etf_entry_technicals,
)
from ..cache import cached_dict, market_cache_ttl, provider_cached
from ..data_integrity import unavailable_payload
from ..qdii_fund_extra import build_qdii_subscription_action, fetch_qdii_fund_meta
from ..utils import (
    TtlCache,
    cn_exchange_prefix,
    normalize_date,
    parse_symbol,
    percentile_of,
    pick_column,
    retry_call,
    safe_float,
    to_ak_date,
    today_str,
)

logger = logging.getLogger(__name__)
_SPOT_CACHE: TtlCache | None = None
_ETF_CACHE: TtlCache | None = None


def _spot_cache() -> TtlCache:
    global _SPOT_CACHE
    if _SPOT_CACHE is None:
        _SPOT_CACHE = TtlCache(ttl_sec=market_cache_ttl())
    return _SPOT_CACHE


def _etf_cache() -> TtlCache:
    global _ETF_CACHE
    if _ETF_CACHE is None:
        _ETF_CACHE = TtlCache(ttl_sec=market_cache_ttl())
    return _ETF_CACHE


def _import_akshare():
    import akshare as ak
    return ak


def _index_code_digits(resolved: str, *, default: str = "000300") -> str:
    code = resolved.split(".")[0]
    return code if code.isdigit() else default


def _ak_index_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("0", "5", "6")) else "sz"
    return f"{prefix}{code}"


def _filter_df_by_yyyymmdd(
    df: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    date_col: str,
) -> pd.DataFrame:
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    start = pd.to_datetime(start_date, format="%Y%m%d", errors="coerce")
    end = pd.to_datetime(end_date, format="%Y%m%d", errors="coerce")
    mask = work[date_col].notna()
    if pd.notna(start):
        mask &= work[date_col] >= start
    if pd.notna(end):
        mask &= work[date_col] <= end
    return work.loc[mask].sort_values(date_col)


def fetch_index_daily_df(
    ak: Any,
    *,
    index_code: str,
    start_date: str,
    end_date: str,
    need_amount: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Fetch index daily bars; fall back when eastmoney push API drops connections."""
    ak_symbol = _ak_index_symbol(index_code)
    errors: list[str] = []
    try:
        df = retry_call(
            lambda: ak.stock_zh_index_daily_em(
                symbol=ak_symbol,
                start_date=start_date,
                end_date=end_date,
            )
        )
        if df is not None and not df.empty:
            return df, "akshare/stock_zh_index_daily_em"
    except Exception as exc:
        errors.append(f"em:{exc}")
        logger.warning("stock_zh_index_daily_em failed for %s: %s", ak_symbol, exc)

    if need_amount:
        try:
            df = retry_call(
                lambda: ak.stock_zh_index_hist_csindex(
                    symbol=index_code,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            if df is not None and not df.empty:
                return df, "akshare/stock_zh_index_hist_csindex"
        except Exception as exc:
            errors.append(f"csindex:{exc}")
            logger.warning("stock_zh_index_hist_csindex failed for %s: %s", index_code, exc)
    else:
        try:
            df = retry_call(lambda: ak.stock_zh_index_daily(symbol=ak_symbol))
            if df is not None and not df.empty:
                work = df.rename(
                    columns={
                        "date": "日期",
                        "open": "开盘",
                        "high": "最高",
                        "low": "最低",
                        "close": "收盘",
                        "volume": "成交量",
                    }
                )
                filtered = _filter_df_by_yyyymmdd(
                    work,
                    start_date=start_date,
                    end_date=end_date,
                    date_col="日期",
                )
                if not filtered.empty:
                    return filtered, "akshare/stock_zh_index_daily"
        except Exception as exc:
            errors.append(f"sina:{exc}")
            logger.warning("stock_zh_index_daily failed for %s: %s", ak_symbol, exc)

    raise ValueError(
        f"index daily unavailable for {index_code}: {'; '.join(errors)[:400]}"
    )


def _normalize_hist_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "换手率": "turnover",
    }
    out = df.rename(columns=rename_map)
    bars: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        date_val = row.get("date")
        if hasattr(date_val, "strftime"):
            date_text = date_val.strftime("%Y-%m-%d")
        else:
            date_text = normalize_date(str(date_val))
        bars.append(
            {
                "date": date_text,
                "open": safe_float(row.get("open")),
                "high": safe_float(row.get("high")),
                "low": safe_float(row.get("low")),
                "close": safe_float(row.get("close")),
                "volume": safe_float(row.get("volume")),
                "amount": safe_float(row.get("amount")),
                "turnover": safe_float(row.get("turnover")),
            }
        )
    return bars


def _spot_row_to_snapshot(row: dict[str, Any], market: str) -> dict[str, Any]:
    code = str(pick_column(row, "代码", "symbol", "code") or "")
    name = str(pick_column(row, "名称", "name") or "")
    return {
        "symbol": code,
        "name": name,
        "market": market,
        "price": safe_float(pick_column(row, "最新价", "price")),
        "change_pct": safe_float(pick_column(row, "涨跌幅", "change_pct")),
        "volume": safe_float(pick_column(row, "成交量", "volume")),
        "amount": safe_float(pick_column(row, "成交额", "amount")),
        "turnover_rate": safe_float(pick_column(row, "换手率", "turnover_rate")),
        "pe_ttm": safe_float(pick_column(row, "市盈率-动态", "市盈率", "pe_ttm")),
        "pb": safe_float(pick_column(row, "市净率", "pb")),
        "market_cap": safe_float(pick_column(row, "总市值", "market_cap")),
        "float_market_cap": safe_float(pick_column(row, "流通市值", "float_market_cap")),
        "high": safe_float(pick_column(row, "最高", "high")),
        "low": safe_float(pick_column(row, "最低", "low")),
        "open": safe_float(pick_column(row, "今开", "open")),
        "prev_close": safe_float(pick_column(row, "昨收", "prev_close")),
        "dividend_yield_pct": safe_float(
            pick_column(row, "股息率", "股息率-TTM", "股息率(TTM)", "股息率TTM")
        ),
    }


class AkshareMarketProvider:
    name = "akshare"
    source = "akshare/eastmoney"

    def _load_cn_a_spot(self) -> pd.DataFrame:
        cache = _spot_cache()
        cached = cache.get("cn_a_spot")
        if cached is not None:
            return cached.copy()
        ak = _import_akshare()
        df = retry_call(lambda: ak.stock_zh_a_spot_em())
        return cache.set("cn_a_spot", df).copy()

    def _load_hk_spot(self) -> pd.DataFrame:
        cache = _spot_cache()
        cached = cache.get("hk_spot")
        if cached is not None:
            return cached.copy()
        ak = _import_akshare()
        df = retry_call(lambda: ak.stock_hk_spot_em())
        return cache.set("hk_spot", df).copy()

    def _load_etf_spot(self) -> pd.DataFrame:
        cache = _etf_cache()
        cached = cache.get("etf_spot")
        if cached is not None:
            return cached.copy()
        ak = _import_akshare()
        df = retry_call(lambda: ak.fund_etf_spot_em())
        return cache.set("etf_spot", df).copy()

    def get_realtime_quote(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        if market_key == "HK":
            df = self._load_hk_spot()
            match = df[df["代码"].astype(str).str.zfill(5) == code.zfill(5)]
        else:
            df = self._load_cn_a_spot()
            match = df[df["代码"].astype(str) == code]
        if match.empty:
            raise ValueError(f"symbol not found: {symbol}")
        snapshot = _spot_row_to_snapshot(match.iloc[0].to_dict(), market_key)
        snapshot["delayed"] = True
        snapshot["source"] = self.source
        snapshot["provider"] = self.name
        snapshot["as_of_date"] = datetime.now().strftime("%Y-%m-%d")
        return snapshot

    def _records_from_financial_df(self, df: pd.DataFrame, *, years: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            item = row.to_dict()
            report_date = pick_column(item, "日期", "REPORT_DATE", "report_date")
            records.append(
                {
                    "report_date": str(report_date)[:10] if report_date is not None else None,
                    "roe": safe_float(pick_column(item, "净资产收益率(%)", "ROE(%)", "ROE")),
                    "gross_margin": safe_float(pick_column(item, "销售毛利率(%)", "毛利率(%)", "毛利率")),
                    "debt_ratio": safe_float(pick_column(item, "资产负债率(%)", "DEBT_ASSET_RATIO(%)")),
                    "net_profit_yoy": safe_float(
                        pick_column(item, "净利润同比增长率(%)", "HOLDER_PROFIT_YOY(%)", "净利润增长率(%)")
                    ),
                    "revenue_yoy": safe_float(
                        pick_column(item, "主营业务收入同比增长率(%)", "营业收入同比增长率(%)", "OPERATING_REVENUE_YOY(%)")
                    ),
                    "ocf_to_net_income": safe_float(
                        pick_column(item, "经营现金流/净利润", "经营净现金流/净利润", "OCF_TO_PROFIT")
                    ),
                }
            )
        records = sorted(records, key=lambda x: x.get("report_date") or "")
        if years > 0:
            records = records[-years:]
        return records

    def get_stock_snapshot(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        snapshot = self.get_realtime_quote(symbol, market)
        code, market_key = parse_symbol(symbol, market)
        if market_key not in {"CN_A", "HK"}:
            snapshot["note"] = "fundamentals not supported for this market"
            return snapshot
        fundamentals = self.get_stock_fundamentals(symbol, years=1, market=market)
        latest = fundamentals.get("records", [{}])[-1] if fundamentals.get("records") else {}
        if latest:
            snapshot.update(
                {
                    "roe": latest.get("roe"),
                    "gross_margin": latest.get("gross_margin"),
                    "debt_ratio": latest.get("debt_ratio"),
                    "net_profit_yoy": latest.get("net_profit_yoy"),
                    "revenue_yoy": latest.get("revenue_yoy"),
                    "financial_report_date": latest.get("report_date"),
                }
            )
        return snapshot

    def get_stock_fundamentals(
        self,
        symbol: str,
        *,
        years: int = 5,
        market: str | None = None,
    ) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        if market_key not in {"CN_A", "HK"}:
            raise ValueError("fundamentals history supports CN_A and HK only")
        ak = _import_akshare()
        if market_key == "HK":
            df = retry_call(
                lambda: ak.stock_financial_hk_analysis_indicator_em(symbol=code, indicator="主要指标")
            )
            source_tag = "akshare/stock_financial_hk_analysis_indicator_em"
        else:
            df = retry_call(lambda: ak.stock_financial_analysis_indicator_em(symbol=code, indicator="主要指标"))
            source_tag = "akshare/stock_financial_analysis_indicator_em"
        if df is None or df.empty:
            raise ValueError(f"fundamentals unavailable: {symbol}")
        records = self._records_from_financial_df(df, years=years)
        extra = enrich_fundamentals_payload(ak, code=code, market_key=market_key, years=years, records=records)
        payload = {
            "symbol": code,
            "market": market_key,
            "years": years,
            "records": records,
            "source": source_tag,
            "provider": self.name,
            "as_of_date": records[-1]["report_date"] if records else today_str(),
        }
        payload.update(extra)
        return payload

    def get_stock_valuation(
        self,
        symbol: str,
        *,
        window_years: int = 5,
        market: str | None = None,
    ) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        snapshot = self.get_realtime_quote(symbol, market)
        ak = _import_akshare()
        pe_history: list[float] = []
        pb_history: list[float] = []
        dividend_yield = None
        if market_key == "CN_A":
            try:
                value_df = retry_call(lambda: ak.stock_value_em(symbol=code))
                if value_df is not None and not value_df.empty:
                    pe_col = [c for c in value_df.columns if "市盈率" in str(c)]
                    if pe_col:
                        pe_history = pd.to_numeric(value_df[pe_col[0]], errors="coerce").dropna().tolist()
            except Exception as exc:
                logger.warning("stock_value_em failed for %s: %s", code, exc)
            try:
                div_df = retry_call(lambda: ak.stock_history_dividend_detail(symbol=code, indicator="分红"))
                if div_df is not None and not div_df.empty and snapshot.get("price"):
                    latest_div = safe_float(div_df.iloc[0].get("派息")) if "派息" in div_df.columns else None
                    if latest_div and snapshot["price"]:
                        dividend_yield = round(latest_div / snapshot["price"] * 100, 2)
            except Exception as exc:
                logger.warning("dividend fetch failed for %s: %s", code, exc)
            ttm_yield = compute_dividend_ttm_yield(ak, code, market_key, snapshot.get("price"))
            if ttm_yield is not None:
                dividend_yield = ttm_yield
        elif market_key == "HK":
            try:
                value_df = retry_call(lambda: ak.stock_hk_indicator_eniu(symbol=code))
                if value_df is not None and not value_df.empty:
                    pe_col = [c for c in value_df.columns if "市盈率" in str(c) or str(c).upper() == "PE"]
                    if pe_col:
                        pe_history = pd.to_numeric(value_df[pe_col[0]], errors="coerce").dropna().tolist()
            except Exception as exc:
                logger.warning("stock_hk_indicator_eniu failed for %s: %s", code, exc)
            try:
                div_df = retry_call(lambda: ak.stock_hk_dividend_payout_em(symbol=code))
                if div_df is not None and not div_df.empty and snapshot.get("price"):
                    div_col = [c for c in div_df.columns if "股息" in str(c) or "派息" in str(c)]
                    if div_col:
                        latest_div = safe_float(div_df.iloc[0][div_col[0]])
                        if latest_div and snapshot["price"]:
                            dividend_yield = round(latest_div / snapshot["price"] * 100, 2)
            except Exception as exc:
                logger.warning("hk dividend fetch failed for %s: %s", code, exc)
            ttm_yield = compute_dividend_ttm_yield(ak, code, market_key, snapshot.get("price"))
            if ttm_yield is not None:
                dividend_yield = ttm_yield
        pe_ttm = snapshot.get("pe_ttm")
        pb = snapshot.get("pb")
        pe_percentile = percentile_of(pe_ttm, pe_history[-window_years * 250 :]) if pe_ttm and pe_history else None
        peg = None
        growth = None
        try:
            fin = self.get_stock_fundamentals(symbol, years=1, market=market)
            growth = fin["records"][-1].get("net_profit_yoy") if fin.get("records") else None
        except Exception as exc:
            logger.warning("fundamentals for valuation failed %s: %s", symbol, exc)
        if pe_ttm and growth and growth > 0:
            peg = round(pe_ttm / growth, 4)
        note = "pe_percentile from akshare historical valuation sample; cross-check tushare/csindex when available"
        if market_key == "HK" and not pe_history:
            note = "HK pe_percentile unavailable from history; using spot PE/PB only"
        return {
            "symbol": code,
            "market": market_key,
            "pe_ttm": pe_ttm,
            "pb": pb,
            "pe_percentile": pe_percentile,
            "percentile_window_years": window_years,
            "dividend_yield_pct": dividend_yield,
            "peg": peg,
            "profit_growth_yoy_pct": growth,
            "source": self.source,
            "provider": self.name,
            "as_of_date": snapshot.get("as_of_date"),
            "note": note,
        }

    def get_bars(
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
        code, market_key = parse_symbol(symbol, market)
        end_date = to_ak_date(end or normalize_date(None))
        if start:
            start_date = to_ak_date(start)
        else:
            days_map = {"1d": 400, "1w": 1500, "1m": 3000, "1m_intraday": 5, "5m_intraday": 5}
            start_date = (datetime.now() - timedelta(days=days_map.get(freq, 400))).strftime("%Y%m%d")
        ak = _import_akshare()
        adjust_map = {"qfq": "qfq", "hfq": "hfq", "none": ""}
        ak_adjust = adjust_map.get(adjust, "qfq")
        if freq in {"1m_intraday", "5m_intraday"}:
            if market_key == "HK":
                raise ValueError("intraday bars for HK are not supported in akshare provider")
            period = "1" if freq == "1m_intraday" else "5"
            prefix = cn_exchange_prefix(code)
            df = retry_call(lambda: ak.stock_zh_a_minute(symbol=f"{prefix}{code}", period=period, adjust=ak_adjust))
            bars = _normalize_hist_df(df)
        elif market_key == "HK":
            period_map = {"1d": "daily", "1w": "weekly", "1m": "monthly"}
            df = retry_call(
                lambda: ak.stock_hk_hist(
                    symbol=code,
                    period=period_map.get(freq, "daily"),
                    start_date=start_date,
                    end_date=end_date,
                    adjust=ak_adjust,
                )
            )
            bars = _normalize_hist_df(df)
        else:
            period_map = {"1d": "daily", "1w": "weekly", "1m": "monthly"}
            df = retry_call(
                lambda: ak.stock_zh_a_hist(
                    symbol=code,
                    period=period_map.get(freq, "daily"),
                    start_date=start_date,
                    end_date=end_date,
                    adjust=ak_adjust,
                )
            )
            bars = _normalize_hist_df(df)
        if limit is not None and len(bars) > limit:
            bars = bars[-limit:]
        return {
            "symbol": code,
            "market": market_key,
            "freq": freq,
            "adjust": adjust,
            "bars": bars,
            "count": len(bars),
            "source": self.source,
            "provider": self.name,
            "as_of_date": bars[-1]["date"] if bars else normalize_date(end),
        }

    def screen_stocks(
        self,
        *,
        market: str = "CN_A",
        filters: dict[str, Any] | None = None,
        wencai_query: str | None = None,
        sort_by: str = "amount",
        limit: int = 50,
    ) -> dict[str, Any]:
        filters = filters or {}
        limit = max(1, min(int(limit or 50), 200))
        query = wencai_query or (self._build_wencai_query(filters) if self._needs_wencai(filters) else None)
        if query:
            return self._screen_with_wencai(query, market=market, limit=limit, filters=filters)
        if market == "HK":
            df = self._load_hk_spot()
        else:
            df = self._load_cn_a_spot()
        rows = [_spot_row_to_snapshot(row.to_dict(), market) for _, row in df.iterrows()]
        filtered = [row for row in rows if self._match_filters(row, filters, market)]
        filtered = self._sort_rows(filtered, sort_by)
        return {
            "market": market,
            "matched_count": len(filtered),
            "filters": filters,
            "stocks": filtered[:limit],
            "source": self.source,
            "provider": self.name,
            "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        }

    def _build_wencai_query(self, filters: dict[str, Any]) -> str | None:
        parts: list[str] = []
        years = int(filters.get("consecutive_years") or filters.get("years") or 0)
        roe_min = safe_float(filters.get("roe_min"))
        gross_min = safe_float(filters.get("gross_margin_min"))
        ocf_min = safe_float(filters.get("ocf_to_net_income_min"))
        if years >= 2 and roe_min is not None:
            parts.append(f"连续{years}年ROE大于{roe_min}%")
        elif roe_min is not None:
            parts.append(f"ROE大于{roe_min}%")
        if years >= 2 and gross_min is not None:
            parts.append(f"连续{years}年毛利率大于{gross_min}%")
        elif gross_min is not None:
            parts.append(f"毛利率大于{gross_min}%")
        if ocf_min is not None:
            parts.append(f"经营现金流除以净利润大于{ocf_min}")
        div_min = safe_float(filters.get("dividend_yield_min"))
        if div_min is not None:
            parts.append(f"股息率大于{div_min}%")
        return "；".join(parts) if parts else None

    def _needs_wencai(self, filters: dict[str, Any]) -> bool:
        keys = ("consecutive_years", "years", "roe_min", "gross_margin_min", "ocf_to_net_income_min")
        return any(filters.get(key) is not None for key in keys)

    def _screen_with_wencai(
        self,
        query: str,
        *,
        market: str,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import pywencai
        text = f"{query}；港股市场" if market == "HK" else query
        try:
            df = retry_call(lambda: pywencai.get(query=text, query_type="stock", loop=True))
        except Exception as exc:
            logger.warning("pywencai query failed: %s", exc)
            df = None
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return {
                "market": market,
                "matched_count": 0,
                "wencai_query": text,
                "filters": filters or {},
                "stocks": [],
                "source": "pywencai",
                "provider": self.name,
                "as_of_date": datetime.now().strftime("%Y-%m-%d"),
            }
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
        stocks: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            item = row.to_dict()
            code = str(pick_column(item, "股票代码", "代码", "symbol") or "")
            name = str(pick_column(item, "股票简称", "名称", "name") or "")
            stocks.append(
                {
                    "symbol": code,
                    "name": name,
                    "market": market,
                    "raw": {str(k): (None if pd.isna(v) else v) for k, v in item.items()},
                }
            )
        return {
            "market": market,
            "matched_count": len(stocks),
            "wencai_query": text,
            "filters": filters or {},
            "stocks": stocks[:limit],
            "source": "pywencai",
            "provider": self.name,
            "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        }

    def _match_filters(self, row: dict[str, Any], filters: dict[str, Any], market: str) -> bool:
        name = row.get("name") or ""
        if filters.get("exclude_st") and ("ST" in name.upper()):
            return False
        checks = [
            ("pe_ttm_min", row.get("pe_ttm"), lambda v, t: v is not None and v >= t),
            ("pe_ttm_max", row.get("pe_ttm"), lambda v, t: v is not None and v <= t),
            ("pb_min", row.get("pb"), lambda v, t: v is not None and v >= t),
            ("pb_max", row.get("pb"), lambda v, t: v is not None and v <= t),
            ("price_min", row.get("price"), lambda v, t: v is not None and v >= t),
            ("price_max", row.get("price"), lambda v, t: v is not None and v <= t),
            ("change_pct_min", row.get("change_pct"), lambda v, t: v is not None and v >= t),
            ("change_pct_max", row.get("change_pct"), lambda v, t: v is not None and v <= t),
            ("turnover_rate_min", row.get("turnover_rate"), lambda v, t: v is not None and v >= t),
            ("amount_min", row.get("amount"), lambda v, t: v is not None and v >= t),
            ("market_cap_min", row.get("market_cap"), lambda v, t: v is not None and v >= t),
            ("market_cap_max", row.get("market_cap"), lambda v, t: v is not None and v <= t),
            ("dividend_yield_min", row.get("dividend_yield_pct"), lambda v, t: v is not None and v >= t),
            ("dividend_yield_max", row.get("dividend_yield_pct"), lambda v, t: v is not None and v <= t),
        ]
        for key, actual, fn in checks:
            target = filters.get(key)
            if target is None:
                continue
            threshold = safe_float(target)
            if threshold is None or not fn(actual, threshold):
                return False
        symbols = filters.get("symbols")
        if symbols and row.get("symbol") not in {str(item).strip() for item in symbols}:
            return False
        return True

    def _sort_rows(self, rows: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
        field_map = {
            "amount": "amount",
            "turnover_rate": "turnover_rate",
            "market_cap": "market_cap",
            "pe_ttm": "pe_ttm",
            "pb": "pb",
            "change_pct": "change_pct",
        }
        field = field_map.get((sort_by or "amount").strip().lower(), "amount")
        return sorted(rows, key=lambda item: item.get(field) or 0, reverse=True)

    def _parse_index_pe_series(
        self,
        pe_df: pd.DataFrame,
        *,
        index: str,
        alias: str,
        resolved: str,
        window_years: int,
        source: str,
    ) -> dict[str, Any]:
        date_col = None
        pe_col = None
        for col in pe_df.columns:
            text = str(col)
            if date_col is None and ("日期" in text or text.lower() == "date"):
                date_col = col
            if pe_col is None and "市盈率" in text:
                pe_col = col
        if date_col is None:
            date_col = pe_df.columns[0]
        if pe_col is None:
            pe_col = pe_df.columns[-2] if len(pe_df.columns) > 1 else pe_df.columns[-1]
        series: list[tuple[str, float]] = []
        for _, row in pe_df.iterrows():
            raw_date = row[date_col]
            if hasattr(raw_date, "strftime"):
                date_text = raw_date.strftime("%Y-%m-%d")
            else:
                date_text = str(raw_date)[:10]
            pe_val = safe_float(row[pe_col])
            if pe_val is not None and date_text:
                series.append((date_text, pe_val))
        if not series:
            raise ValueError(f"index valuation unavailable: {index}")
        series.sort(key=lambda item: item[0])
        cutoff = (datetime.now() - timedelta(days=365 * max(window_years, 1))).strftime("%Y-%m-%d")
        window = [pe for dt, pe in series if dt >= cutoff]
        if not window:
            window = [pe for _, pe in series[-250:]]
        latest_date, latest_pe = series[-1]
        return {
            "index": index,
            "index_name": alias,
            "resolved_index": resolved,
            "pe_ttm": latest_pe,
            "pe_percentile": percentile_of(latest_pe, window) if latest_pe is not None else None,
            "percentile_window_years": window_years,
            "sample_size": len(window),
            "latest_date": latest_date,
            "source": source,
            "provider": self.name,
            "note": "fallback source; tushare/csindex preferred when configured",
        }

    @provider_cached(
        lambda self, index, window_years=5, **_: (
            f"index_val:{resolve_index(index)}:{max(1, min(int(window_years or 5), 10))}"
        )
    )
    def get_index_valuation(self, index: str, *, window_years: int = 5) -> dict[str, Any]:
        resolved = resolve_index(index)
        alias = INDEX_ALIASES.get(resolved, GLOBAL_INDEX_EM_NAMES.get(resolved, resolved))
        if is_global_index(index):
            return self._get_global_index_valuation(index, alias, resolved, window_years=window_years)
        if is_hsi_index(index):
            return self._get_hsi_index_valuation(index, alias, resolved, window_years=window_years)
        ak = _import_akshare()
        try:
            pe_df = retry_call(lambda: ak.stock_index_pe_lg(symbol=alias))
            if pe_df is not None and not pe_df.empty:
                return self._parse_index_pe_series(
                    pe_df,
                    index=index,
                    alias=alias,
                    resolved=resolved,
                    window_years=window_years,
                    source="akshare/stock_index_pe_lg",
                )
        except Exception as exc:
            logger.warning("stock_index_pe_lg failed for %s: %s", index, exc)
        cs_code = resolved.split(".")[0]
        if not cs_code.isdigit():
            cs_code = "".join(ch for ch in resolved if ch.isdigit()) or resolved
        pe_df = retry_call(lambda: ak.stock_zh_index_value_csindex(symbol=cs_code))
        if pe_df is None or pe_df.empty:
            raise ValueError(f"index valuation unavailable: {index}")
        return self._parse_index_pe_series(
            pe_df,
            index=index,
            alias=alias,
            resolved=resolved,
            window_years=window_years,
            source="akshare/stock_zh_index_value_csindex",
        )

    def _get_hsi_index_valuation(
        self,
        index: str,
        alias: str,
        resolved: str,
        *,
        window_years: int,
    ) -> dict[str, Any]:
        ak = _import_akshare()
        pe_ttm = None
        latest_date = today_str()
        pe_series: list[float] = []
        try:
            spot_df = retry_call(lambda: ak.stock_hk_index_spot_em())
            if spot_df is not None and not spot_df.empty:
                name_col = "名称" if "名称" in spot_df.columns else spot_df.columns[1]
                match = spot_df[spot_df[name_col].astype(str).str.contains("恒生", na=False)]
                if match.empty:
                    code_col = "代码" if "代码" in spot_df.columns else spot_df.columns[0]
                    match = spot_df[spot_df[code_col].astype(str).str.upper().isin({"HSI", "HSCEI"})]
                if not match.empty:
                    row = match.iloc[0].to_dict()
                    pe_ttm = safe_float(pick_column(row, "市盈率", "PE", "pe_ttm"))
                    latest_date = str(pick_column(row, "最新价", "日期") or latest_date)[:10]
        except Exception as exc:
            logger.warning("hsi spot valuation failed: %s", exc)
        try:
            hist_df = retry_call(lambda: ak.index_global_hist_em(symbol="恒生指数"))
            if hist_df is not None and not hist_df.empty:
                pe_col = next((c for c in hist_df.columns if "市盈率" in str(c)), None)
                date_col = "日期" if "日期" in hist_df.columns else hist_df.columns[0]
                if pe_col:
                    frame = hist_df.copy()
                    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
                    frame = frame.dropna(subset=[date_col]).sort_values(date_col)
                    cutoff = datetime.now() - timedelta(days=365 * max(window_years, 1))
                    window = frame[frame[date_col] >= cutoff] if not frame.empty else frame
                    if window.empty:
                        window = frame.tail(max(250, window_years * 50))
                    pe_series = pd.to_numeric(window[pe_col], errors="coerce").dropna().tolist()
                    if pe_ttm is None and pe_series:
                        pe_ttm = pe_series[-1]
                    if not latest_date and not frame.empty:
                        latest = frame.iloc[-1][date_col]
                        latest_date = latest.strftime("%Y-%m-%d") if hasattr(latest, "strftime") else str(latest)[:10]
        except Exception as exc:
            logger.warning("hsi global hist failed: %s", exc)
        if pe_ttm is None:
            raise ValueError("HSI index valuation unavailable; configure Wind/Tushare for fallback")
        return {
            "index": index,
            "index_name": alias,
            "resolved_index": resolved,
            "pe_ttm": pe_ttm,
            "pe_percentile": percentile_of(pe_ttm, pe_series) if pe_ttm and pe_series else None,
            "percentile_window_years": window_years,
            "sample_size": len(pe_series),
            "latest_date": latest_date,
            "source": "akshare/stock_hk_index_spot_em+index_global_hist_em",
            "provider": self.name,
            "note": "HSI PE history from index_global_hist_em when available; Wind/Tushare preferred",
        }

    def _get_global_index_valuation(
        self,
        index: str,
        alias: str,
        resolved: str,
        *,
        window_years: int,
    ) -> dict[str, Any]:
        ak = _import_akshare()
        em_name = global_index_em_name(index)
        pe_ttm = None
        latest_date = today_str()
        pe_series: list[float] = []
        try:
            spot_df = retry_call(lambda: ak.index_global_spot_em())
            if spot_df is not None and not spot_df.empty:
                name_col = "名称" if "名称" in spot_df.columns else spot_df.columns[0]
                match = spot_df[spot_df[name_col].astype(str).str.contains(em_name.replace("德国", ""), na=False)]
                if match.empty:
                    match = spot_df[spot_df[name_col].astype(str) == em_name]
                if not match.empty:
                    row = match.iloc[0].to_dict()
                    pe_ttm = safe_float(pick_column(row, "市盈率", "PE", "pe_ttm"))
        except Exception as exc:
            logger.warning("global index spot failed for %s: %s", em_name, exc)
        try:
            hist_df = retry_call(lambda: ak.index_global_hist_em(symbol=em_name))
            if hist_df is not None and not hist_df.empty:
                pe_col = next((c for c in hist_df.columns if "市盈率" in str(c)), None)
                date_col = "日期" if "日期" in hist_df.columns else hist_df.columns[0]
                if pe_col:
                    frame = hist_df.copy()
                    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
                    frame = frame.dropna(subset=[date_col]).sort_values(date_col)
                    cutoff = datetime.now() - timedelta(days=365 * max(window_years, 1))
                    window = frame[frame[date_col] >= cutoff]
                    if window.empty:
                        window = frame.tail(max(250, window_years * 50))
                    pe_series = pd.to_numeric(window[pe_col], errors="coerce").dropna().tolist()
                    if pe_ttm is None and pe_series:
                        pe_ttm = pe_series[-1]
                    latest = frame.iloc[-1][date_col]
                    latest_date = latest.strftime("%Y-%m-%d") if hasattr(latest, "strftime") else str(latest)[:10]
        except Exception as exc:
            logger.warning("global index hist failed for %s: %s", em_name, exc)
        if pe_ttm is None:
            raise ValueError(f"global index valuation unavailable: {index}")
        return {
            "index": index,
            "index_name": em_name,
            "resolved_index": resolved,
            "pe_ttm": pe_ttm,
            "pe_percentile": percentile_of(pe_ttm, pe_series) if pe_ttm and pe_series else None,
            "percentile_window_years": window_years,
            "sample_size": len(pe_series),
            "latest_date": latest_date,
            "source": "akshare/index_global_spot_em+index_global_hist_em",
            "provider": self.name,
            "note": "overseas index PE; percentile requires PE history column from eastmoney",
        }

    @provider_cached(lambda self, indicator="cn_10y", **_: f"macro:{(indicator or 'cn_10y').strip().lower()}")
    def get_macro_rate(self, indicator: str = "cn_10y") -> dict[str, Any]:
        indicator = (indicator or "cn_10y").strip().lower()
        ak = _import_akshare()
        if indicator == "cn_10y":
            return self._get_cn_10y_yield(ak, indicator)
        if indicator == "dr007":
            return self._get_dr007(ak)
        if indicator in {"shibor_1w", "shibor_1m"}:
            return self._get_shibor(ak, indicator)
        if indicator == "usdcny":
            return self._get_usdcny(ak)
        if indicator == "tsf_yoy":
            return self._get_tsf_yoy(ak)
        if indicator == "gc001":
            return self._get_gc001(ak)
        if indicator == "mlf":
            return self._get_mlf(ak)
        if indicator == "lpr_1y":
            return self._get_lpr(ak, tenor="1y")
        if indicator == "lpr_5y":
            return self._get_lpr(ak, tenor="5y")
        if indicator == "us_10y":
            return self._get_us_10y(ak)
        if indicator == "cn_1y":
            return self._get_cn_1y_yield(ak)
        if indicator == "ncd_1y":
            return self._get_ncd_1y(ak)
        raise ValueError(f"unsupported macro indicator: {indicator}")

    def _get_cn_10y_yield(self, ak: Any, indicator: str) -> dict[str, Any]:
        df = retry_call(lambda: ak.bond_china_yield())
        if df is None or df.empty:
            raise ValueError("macro rate unavailable")
        target_col = self._pick_yield_column(df.columns, year_hint="10")
        latest = df.iloc[-1]
        value = safe_float(latest.get(target_col))
        date_val = latest.get("日期") if "日期" in latest else latest.iloc[0]
        return {
            "indicator": indicator,
            "value_pct": value,
            "date": str(date_val)[:10],
            "source": "akshare/bond_china_yield",
            "provider": self.name,
            "note": "use for ERP estimation with index PE",
        }

    @staticmethod
    def _pick_yield_column(columns: Any, *, year_hint: str, country_hint: str | None = None) -> Any:
        cols = list(columns)
        for col in cols:
            text = str(col)
            if country_hint and country_hint not in text:
                continue
            if year_hint in text and "年" in text:
                return col
        for col in cols:
            text = str(col)
            if year_hint in text:
                return col
        return cols[-1]

    def _get_cn_1y_yield(self, ak: Any) -> dict[str, Any]:
        df = retry_call(lambda: ak.bond_china_yield())
        if df is None or df.empty:
            raise ValueError("cn_1y unavailable")
        target_col = self._pick_yield_column(df.columns, year_hint="1")
        latest = df.iloc[-1]
        value = safe_float(latest.get(target_col))
        date_val = latest.get("日期") if "日期" in latest else latest.iloc[0]
        return {
            "indicator": "cn_1y",
            "value_pct": value,
            "date": str(date_val)[:10],
            "source": "akshare/bond_china_yield",
            "provider": self.name,
        }

    @staticmethod
    def _extract_mlf_rate(row: dict[str, Any]) -> float | None:
        keys_upper = {str(key).upper(): key for key in row.keys()}
        if any(name in keys_upper for name in ("FDR007", "DR007")):
            mlf_key = next((keys_upper[item] for item in keys_upper if "MLF" in item), None)
            if mlf_key is None:
                return None
        for key in row.keys():
            if "MLF" in str(key).upper():
                value = safe_float(row[key])
                if value is not None:
                    return value
        for name in ("RATE", "利率", "value"):
            value = safe_float(pick_column(row, name))
            if value is not None:
                return value
        return None

    def _get_mlf(self, ak: Any) -> dict[str, Any]:
        for symbol in ("MLF", "MLF001", "MLF007"):
            try:
                df = retry_call(lambda s=symbol: ak.repo_rate_query(symbol=s))
                if df is None or df.empty:
                    continue
                latest = df.iloc[-1].to_dict()
                value = self._extract_mlf_rate(latest)
                date_val = pick_column(latest, "date", "日期", "report_date")
                if value is not None:
                    return {
                        "indicator": "mlf",
                        "value_pct": value,
                        "date": str(date_val)[:10] if date_val is not None else today_str(),
                        "source": f"akshare/repo_rate_query/{symbol}",
                        "provider": self.name,
                    }
            except Exception as exc:
                logger.warning("mlf repo_rate_query %s failed: %s", symbol, exc)
        raise ValueError(
            "mlf unavailable: no official MLF rate series from provider; "
            "use web_fetch chinamoney.com.cn or Wind/Choice"
        )

    def _get_lpr(self, ak: Any, *, tenor: str) -> dict[str, Any]:
        df = retry_call(lambda: ak.macro_china_lpr())
        if df is None or df.empty:
            raise ValueError(f"lpr_{tenor} unavailable")
        date_col = next(
            (col for col in df.columns if "DATE" in str(col).upper() or "日期" in str(col)),
            df.columns[0],
        )
        col_key = "LPR1Y" if tenor == "1y" else "LPR5Y"
        rate_col = next((col for col in df.columns if col_key in str(col).upper()), None)
        if rate_col is None:
            raise ValueError(f"lpr_{tenor} unavailable")
        latest = df.iloc[-1]
        return {
            "indicator": f"lpr_{tenor}",
            "value_pct": safe_float(latest.get(rate_col)),
            "date": str(latest.get(date_col))[:10],
            "source": "akshare/macro_china_lpr",
            "provider": self.name,
        }

    def _get_us_10y(self, ak: Any) -> dict[str, Any]:
        df = retry_call(lambda: ak.bond_zh_us_rate(start_date="20000101"))
        if df is None or df.empty:
            raise ValueError("us_10y unavailable")
        date_col = df.columns[0]
        target_col = self._pick_yield_column(df.columns, year_hint="10", country_hint="美国")
        if target_col == date_col:
            target_col = self._pick_yield_column(df.columns, year_hint="10")
        latest = df.dropna(subset=[target_col]).iloc[-1]
        return {
            "indicator": "us_10y",
            "value_pct": safe_float(latest.get(target_col)),
            "date": str(latest.get(date_col))[:10],
            "source": "akshare/bond_zh_us_rate",
            "provider": self.name,
            "note": "US treasury 10Y; overseas allocation halving rule when >4.5%",
        }

    def _get_dr007(self, ak: Any) -> dict[str, Any]:
        df = retry_call(lambda: ak.repo_rate_query(symbol="DR007"))
        if df is None or df.empty:
            raise ValueError(
                "dr007 unavailable: repo_rate_query returned empty; "
                "use web_fetch chinamoney.com.cn"
            )
        latest = df.iloc[-1].to_dict()
        value = safe_float(pick_column(latest, "FDR007", "DR007", "value"))
        date_val = pick_column(latest, "date", "日期", "report_date")
        if value is None:
            raise ValueError("dr007 unavailable: missing rate column")
        return {
            "indicator": "dr007",
            "value_pct": value,
            "date": str(date_val)[:10] if date_val is not None else today_str(),
            "source": "akshare/repo_rate_query/DR007",
            "provider": self.name,
        }

    def _get_shibor(self, ak: Any, indicator: str) -> dict[str, Any]:
        df = retry_call(lambda: ak.macro_china_shibor_all())
        if df is None or df.empty:
            raise ValueError(f"{indicator} unavailable")
        col_map = {"shibor_1w": "1W", "shibor_1m": "1M"}
        target = col_map.get(indicator, "1W")
        col = next((c for c in df.columns if target in str(c).upper()), None)
        if col is None:
            raise ValueError(f"{indicator} unavailable")
        latest = df.iloc[-1]
        date_val = pick_column(latest.to_dict(), "日期", "date")
        return {
            "indicator": indicator,
            "value_pct": safe_float(latest.get(col)),
            "date": str(date_val)[:10] if date_val is not None else today_str(),
            "source": "akshare/macro_china_shibor_all",
            "provider": self.name,
        }

    def _get_usdcny(self, ak: Any) -> dict[str, Any]:
        try:
            df = retry_call(lambda: ak.currency_boc_safe())
        except Exception as exc:
            logger.warning("currency_boc_safe failed: %s", exc)
            df = None
        if df is not None and not df.empty:
            latest = df.iloc[-1].to_dict()
            value = safe_float(pick_column(latest, "美元", "USD", "现汇卖出价"))
            date_val = pick_column(latest, "日期", "date")
            if value is not None:
                return {
                    "indicator": "usdcny",
                    "value_pct": value,
                    "date": str(date_val)[:10] if date_val is not None else today_str(),
                    "source": "akshare/currency_boc_safe",
                    "provider": self.name,
                    "note": "BOC safe middle/reference rate",
                }
        spot_df = retry_call(lambda: ak.fx_spot_quote())
        if spot_df is None or spot_df.empty:
            raise ValueError("usdcny unavailable")
        match = spot_df[spot_df.iloc[:, 0].astype(str).str.contains("USD/CNY", na=False)]
        if match.empty:
            match = spot_df.head(1)
        row = match.iloc[0].to_dict()
        return {
            "indicator": "usdcny",
            "value_pct": safe_float(pick_column(row, "买报价", "最新价", "close")),
            "date": today_str(),
            "source": "akshare/fx_spot_quote",
            "provider": self.name,
        }

    def _get_tsf_yoy(self, ak: Any) -> dict[str, Any]:
        df = retry_call(lambda: ak.macro_china_new_financial_credit())
        if df is None or df.empty:
            raise ValueError("tsf_yoy unavailable")
        cols = list(df.columns)
        date_col = cols[0]
        yoy_col = next(
            (col for col in cols if "同比" in str(col) and "累计" not in str(col)),
            cols[2] if len(cols) > 2 else None,
        )
        if yoy_col is None:
            raise ValueError("tsf_yoy unavailable")
        ordered = df.copy()
        yoy_values: list[float] = []
        dates: list[str] = []
        for _, row in ordered.iterrows():
            yoy = safe_float(row.get(yoy_col))
            if yoy is None:
                continue
            yoy_values.append(yoy)
            dates.append(str(row.get(date_col))[:10])
        if not yoy_values:
            raise ValueError("tsf_yoy unavailable")
        latest_yoy = yoy_values[0]
        history = yoy_values[:36]
        percentile = percentile_of(latest_yoy, history) if len(history) >= 6 else None
        declining_2m = len(yoy_values) >= 2 and yoy_values[0] < yoy_values[1]
        if len(yoy_values) >= 3:
            declining_2m = declining_2m and yoy_values[1] < yoy_values[2]
        low_percentile = percentile is not None and percentile <= 30.0
        return {
            "indicator": "tsf_yoy",
            "value_pct": latest_yoy,
            "date": dates[0] if dates else today_str(),
            "percentile_3y": percentile,
            "tsf_yoy_declining_2m": declining_2m,
            "tsf_yoy_low_percentile_3y": low_percentile,
            "recent_yoy": [
                {"date": dates[idx], "value_pct": yoy_values[idx]}
                for idx in range(min(3, len(yoy_values)))
            ],
            "source": "akshare/macro_china_new_financial_credit",
            "provider": self.name,
            "note": "monthly TSF YoY; used by china-market-strategy monetary linkage",
        }

    def _get_gc001(self, ak: Any) -> dict[str, Any]:
        df = retry_call(lambda: ak.bond_sh_buy_back_em())
        if df is None or df.empty:
            raise ValueError("gc001 unavailable")
        code_col = next((col for col in df.columns if "代码" in str(col) or "品种" in str(col)), df.columns[0])
        rate_col = next(
            (col for col in df.columns if any(k in str(col) for k in ("利率", "收益率", "加权"))),
            df.columns[-1],
        )
        match = df[df[code_col].astype(str).str.upper().str.contains("GC001", na=False)]
        if match.empty:
            match = df.head(1)
        row = match.iloc[0].to_dict()
        value = safe_float(row.get(rate_col))
        if value is None:
            value = safe_float(pick_column(row, "利率", "加权平均利率", "最新价"))
        if value is None:
            raise ValueError("gc001 unavailable")
        return {
            "indicator": "gc001",
            "value_pct": value,
            "date": today_str(),
            "source": "akshare/bond_sh_buy_back_em",
            "provider": self.name,
            "note": "Shanghai exchange 1-day repo GC001",
        }

    def _get_ncd_1y(self, ak: Any) -> dict[str, Any]:
        raise ValueError(
            "ncd_1y unavailable: no AAA NCD 1Y series in provider; "
            "use web_fetch chinamoney/chinabond or Wind/Choice"
        )

    def _fetch_short_bond_funds(self, ak: Any, *, top_n: int = 10) -> list[dict[str, Any]]:
        rank_df = retry_call(lambda: ak.fund_open_fund_rank_em(symbol="债券型"))
        if rank_df is None or rank_df.empty:
            return []
        name_col = next((col for col in rank_df.columns if "简称" in str(col) or "名称" in str(col)), rank_df.columns[2])
        code_col = next((col for col in rank_df.columns if "代码" in str(col)), rank_df.columns[1])
        m1_col = next((col for col in rank_df.columns if "近1月" in str(col) or "1月" == str(col)), None)
        m3_col = next((col for col in rank_df.columns if "近3月" in str(col) or "3月" == str(col)), None)
        scale_col = next((col for col in rank_df.columns if "规模" in str(col)), None)
        keywords = ("短债", "纯债", "超短", "中短债")
        candidates: list[dict[str, Any]] = []
        for _, row in rank_df.iterrows():
            item = row.to_dict()
            name = str(item.get(name_col) or "")
            if not any(keyword in name for keyword in keywords):
                continue
            m1 = safe_float(item.get(m1_col)) if m1_col else None
            if m1 is None:
                continue
            candidates.append(
                {
                    "symbol": str(item.get(code_col) or "").strip(),
                    "name": name,
                    "return_1m_pct": m1,
                    "return_3m_pct": safe_float(item.get(m3_col)) if m3_col else None,
                    "scale": safe_float(item.get(scale_col)) if scale_col else None,
                }
            )
        candidates.sort(key=lambda fund: fund.get("return_1m_pct") or 0, reverse=True)
        return candidates[:top_n]

    def _compute_dr007_monthly_avg(self, ak: Any) -> dict[str, Any]:
        df = retry_call(lambda: ak.repo_rate_query(symbol="DR007"))
        if df is None or df.empty:
            raise ValueError("dr007 history unavailable")
        value_col = next((col for col in df.columns if "FDR007" in str(col).upper() or "DR007" in str(col).upper()), df.columns[1])
        date_col = next((col for col in df.columns if "date" in str(col).lower() or "日期" in str(col)), df.columns[0])
        work = df[[date_col, value_col]].tail(22).copy()
        values = pd.to_numeric(work[value_col], errors="coerce").dropna().tolist()
        if not values:
            raise ValueError("dr007 history unavailable")
        avg = round(sum(values) / len(values), 4)
        return {
            "dr007_monthly_avg_pct": avg,
            "dr007_below_1_5": avg < 1.5,
            "sample_days": len(values),
            "latest_date": str(work.iloc[-1][date_col])[:10],
        }

    @provider_cached(lambda self, top_n=10, **_: f"cash_snapshot:{max(3, min(int(top_n or 10), 30))}")
    def get_cash_market_snapshot(self, *, top_n: int = 10) -> dict[str, Any]:
        top_n = max(3, min(int(top_n or 10), 30))
        ak = _import_akshare()
        gc001 = self.get_macro_rate("gc001")
        dr007 = self.get_macro_rate("dr007")
        cn_1y = None
        ncd_1y = None
        dr007_monthly = None
        short_bond_funds: list[dict[str, Any]] = []
        try:
            cn_1y = self.get_macro_rate("cn_1y")
        except Exception as exc:
            logger.warning("cn_1y fetch failed: %s", exc)
        try:
            ncd_1y = self.get_macro_rate("ncd_1y")
        except Exception as exc:
            logger.warning("ncd_1y fetch failed: %s", exc)
            ncd_1y = unavailable_payload(
                reason="no_official_ncd_1y_series",
                web_hint="web_fetch chinamoney/chinabond or Wind/Choice",
            )
        try:
            dr007_monthly = cached_dict(
                "macro:dr007_monthly",
                lambda: self._compute_dr007_monthly_avg(ak),
            )
        except Exception as exc:
            logger.warning("dr007 monthly avg failed: %s", exc)
        try:
            short_bond_funds = self._fetch_short_bond_funds(ak, top_n=top_n)
        except Exception as exc:
            logger.warning("short bond fund rank failed: %s", exc)
        rank_df = retry_call(lambda: ak.fund_money_rank_em())
        if rank_df is None or rank_df.empty:
            raise ValueError("money fund rank unavailable")
        name_col = next((col for col in rank_df.columns if "名称" in str(col)), rank_df.columns[1])
        code_col = next((col for col in rank_df.columns if "代码" in str(col)), rank_df.columns[0])
        yield_col = next(
            (col for col in rank_df.columns if "7日" in str(col) or "七日" in str(col) or "年化" in str(col)),
            None,
        )
        scale_col = next((col for col in rank_df.columns if "规模" in str(col)), None)
        funds: list[dict[str, Any]] = []
        for _, row in rank_df.head(top_n).iterrows():
            item = row.to_dict()
            funds.append(
                {
                    "symbol": str(item.get(code_col) or "").strip(),
                    "name": str(item.get(name_col) or "").strip(),
                    "yield_7d_pct": safe_float(item.get(yield_col)) if yield_col else None,
                    "scale": safe_float(item.get(scale_col)) if scale_col else None,
                }
            )
        yields = [f["yield_7d_pct"] for f in funds if f.get("yield_7d_pct") is not None]
        top3_avg = round(sum(yields[:3]) / len(yields[:3]), 4) if len(yields) >= 3 else None
        gc001_rate = gc001.get("value_pct")
        prefer_repo = (
            gc001_rate is not None
            and top3_avg is not None
            and gc001_rate > top3_avg + 0.5
        )
        short_top3_avg_1m = None
        short_returns = [f["return_1m_pct"] for f in short_bond_funds if f.get("return_1m_pct") is not None]
        if len(short_returns) >= 3:
            short_top3_avg_1m = round(sum(short_returns[:3]) / 3, 4)
        prefer_short_bond_over_money = (
            short_top3_avg_1m is not None
            and top3_avg is not None
            and short_top3_avg_1m > top3_avg + 0.8
        )
        deposit_benchmark = self._deposit_rate_benchmark_unavailable()
        return {
            "as_of_date": today_str(),
            "gc001": gc001,
            "dr007": {
                "value_pct": dr007.get("value_pct"),
                "date": dr007.get("date"),
            },
            "cn_1y": cn_1y,
            "ncd_1y": ncd_1y,
            "dr007_monthly": dr007_monthly,
            "money_funds_top": funds,
            "money_fund_top3_avg_yield_7d_pct": top3_avg,
            "short_bond_funds_top": short_bond_funds,
            "short_bond_top3_avg_return_1m_pct": short_top3_avg_1m,
            "prefer_repo_over_money_fund": prefer_repo,
            "prefer_short_bond_over_money_fund": prefer_short_bond_over_money,
            "deposit_rate_benchmark": deposit_benchmark,
            "repo_vs_fund_spread_pct": round(gc001_rate - top3_avg, 4)
            if gc001_rate is not None and top3_avg is not None
            else None,
            "source": "akshare/bond_sh_buy_back_em+fund_money_rank_em+fund_open_fund_rank_em+repo_rate_query",
            "provider": self.name,
            "note": "deposit_rate_benchmark and ncd_1y may be available:false; use web_fetch when missing",
        }

    @provider_cached(
        lambda self, window_years=1, index="000985", **_: (
            f"liquidity:{resolve_index(index)}:{max(1, min(int(window_years or 1), 5))}"
        )
    )
    def get_market_liquidity(self, *, window_years: int = 1, index: str = "000985") -> dict[str, Any]:
        window_years = max(1, min(int(window_years or 1), 5))
        resolved = resolve_index(index)
        ak = _import_akshare()
        index_code = _index_code_digits(resolved, default="000985")
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365 * window_years + 30)).strftime("%Y%m%d")
        df, daily_source = fetch_index_daily_df(
            ak,
            index_code=index_code,
            start_date=start_date,
            end_date=end_date,
            need_amount=True,
        )
        if df is None or df.empty:
            raise ValueError("market liquidity unavailable")
        date_col = next((c for c in df.columns if "日期" in str(c) or str(c).lower() == "date"), df.columns[0])
        amount_col = next(
            (
                c
                for c in df.columns
                if any(k in str(c) for k in ("成交额", "成交金额", "amount", "turnover"))
            ),
            None,
        )
        if amount_col is None:
            for col in reversed(list(df.columns)):
                if col == date_col:
                    continue
                series = pd.to_numeric(df[col], errors="coerce").dropna()
                if len(series) >= 5 and float(series.median()) >= 1e8:
                    amount_col = col
                    break
        if amount_col is None:
            raise ValueError("market liquidity amount column missing")
        amounts = pd.to_numeric(df[amount_col], errors="coerce").dropna().tolist()
        if not amounts:
            raise ValueError("market liquidity series empty")
        latest_row = df.iloc[-1]
        latest_amount = safe_float(latest_row.get(amount_col))
        latest_date = str(latest_row.get(date_col))[:10]
        percentile = percentile_of(latest_amount, amounts) if latest_amount is not None else None
        avg_20d = round(sum(amounts[-20:]) / min(len(amounts), 20), 2) if amounts else None
        return {
            "index": index,
            "resolved_index": resolved,
            "latest_turnover": latest_amount,
            "avg_turnover_20d": avg_20d,
            "turnover_percentile": percentile,
            "percentile_window_years": window_years,
            "sample_size": len(amounts),
            "latest_date": latest_date,
            "source": daily_source,
            "provider": self.name,
            "note": "liquidity exhaustion when turnover_percentile < 20 for 5 consecutive days (check series manually)",
        }

    @provider_cached(lambda self, **_: "cross_market")
    def get_cross_market_indicators(self) -> dict[str, Any]:
        ak = _import_akshare()
        ah_premium_avg = None
        ah_count = 0
        try:
            ah_df = retry_call(lambda: ak.stock_zh_ah_spot())
            if ah_df is not None and not ah_df.empty:
                premium_col = next((c for c in ah_df.columns if "溢价" in str(c)), None)
                if premium_col:
                    premiums = pd.to_numeric(ah_df[premium_col], errors="coerce").dropna().tolist()
                    if premiums:
                        ah_premium_avg = round(sum(premiums) / len(premiums), 2)
                        ah_count = len(premiums)
        except Exception as exc:
            logger.warning("ah premium fetch failed: %s", exc)
        usdcny = None
        usdcny_date = today_str()
        usdcny_monthly_change_pct = None
        usd_strengthening_5pct_month = False
        cny_depreciation_3pct_month = False
        try:
            fx = self.get_macro_rate("usdcny")
            usdcny = fx.get("value_pct")
            usdcny_date = fx.get("date", usdcny_date)
            fx_change = cached_dict(
                "macro:usdcny_monthly_change",
                lambda: self._compute_usdcny_monthly_change(ak),
            )
            usdcny_monthly_change_pct = fx_change.get("monthly_change_pct")
            usd_strengthening_5pct_month = bool(fx_change.get("usd_strengthening_5pct_month"))
            cny_depreciation_3pct_month = bool(fx_change.get("cny_depreciation_3pct_month"))
        except Exception as exc:
            logger.warning("usdcny fetch failed: %s", exc)
        us_10y = None
        us_10y_date = None
        us_10y_above_4_5 = False
        try:
            us_payload = self.get_macro_rate("us_10y")
            us_10y = us_payload.get("value_pct")
            us_10y_date = us_payload.get("date")
            us_10y_above_4_5 = us_10y is not None and us_10y > 4.5
        except Exception as exc:
            logger.warning("us_10y fetch failed: %s", exc)
        dxy = None
        dxy_date = None
        dxy_monthly_change_pct = None
        try:
            dxy_payload = cached_dict("macro:dxy", lambda: self._get_dxy(ak))
            dxy = dxy_payload.get("value")
            dxy_date = dxy_payload.get("date")
            dxy_monthly_change_pct = dxy_payload.get("monthly_change_pct")
        except Exception as exc:
            logger.warning("dxy fetch failed: %s", exc)
        return {
            "ah_premium_avg_pct": ah_premium_avg,
            "ah_pairs_count": ah_count,
            "usdcny": usdcny,
            "usdcny_date": usdcny_date,
            "usdcny_monthly_change_pct": usdcny_monthly_change_pct,
            "usd_strengthening_5pct_month": usd_strengthening_5pct_month,
            "cny_depreciation_3pct_month": cny_depreciation_3pct_month,
            "us_10y": us_10y,
            "us_10y_date": us_10y_date,
            "us_10y_above_4_5": us_10y_above_4_5,
            "dxy": dxy,
            "dxy_date": dxy_date,
            "dxy_monthly_change_pct": dxy_monthly_change_pct,
            "source": "akshare/stock_zh_ah_spot+currency+bond_zh_us_rate+index_global",
            "provider": self.name,
            "as_of_date": today_str(),
        }

    def _compute_usdcny_monthly_change(self, ak: Any) -> dict[str, Any]:
        df = retry_call(lambda: ak.currency_boc_safe())
        if df is None or df.empty:
            raise ValueError("usdcny history unavailable")
        date_col = next((col for col in df.columns if "日期" in str(col)), df.columns[0])
        usd_col = next((col for col in df.columns if "美元" in str(col)), None)
        if usd_col is None:
            raise ValueError("usdcny history unavailable")
        work = df[[date_col, usd_col]].copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work[usd_col] = pd.to_numeric(work[usd_col], errors="coerce")
        work = work.dropna().sort_values(date_col)
        if len(work) < 22:
            raise ValueError("usdcny history too short")
        latest = work.iloc[-1]
        month_ago = work.iloc[-22]
        latest_val = safe_float(latest[usd_col])
        month_val = safe_float(month_ago[usd_col])
        if latest_val is None or month_val is None or month_val == 0:
            raise ValueError("usdcny history invalid")
        change_pct = round((latest_val - month_val) / month_val * 100, 4)
        return {
            "monthly_change_pct": change_pct,
            "usd_strengthening_5pct_month": change_pct >= 5.0,
            "cny_depreciation_3pct_month": change_pct >= 3.0,
            "latest_usdcny": latest_val,
            "month_ago_usdcny": month_val,
            "latest_date": str(latest[date_col])[:10],
            "month_ago_date": str(month_ago[date_col])[:10],
        }

    @staticmethod
    def _deposit_rate_benchmark_unavailable() -> dict[str, Any]:
        return unavailable_payload(
            reason="no_official_deposit_rate_feed",
            web_hint="web_fetch PBOC benchmark or major bank rate pages",
        )

    def _get_dxy(self, ak: Any) -> dict[str, Any]:
        hist_df = retry_call(lambda: ak.index_global_hist_em(symbol="美元指数"))
        if hist_df is None or hist_df.empty:
            raise ValueError(
                "dxy unavailable: index_global_hist_em returned empty; use web_fetch official FX source"
            )
        date_col = next((c for c in hist_df.columns if "日期" in str(c) or "date" in str(c).lower()), hist_df.columns[0])
        close_col = next(
            (c for c in hist_df.columns if str(c).lower() in {"close", "收盘", "最新价"} or "收盘" in str(c)),
            hist_df.columns[-1],
        )
        work = hist_df.copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work[close_col] = pd.to_numeric(work[close_col], errors="coerce")
        work = work.dropna(subset=[date_col, close_col]).sort_values(date_col)
        if work.empty:
            raise ValueError("dxy unavailable: empty history after normalization")
        latest = work.iloc[-1]
        month_ago = work.iloc[-22] if len(work) >= 22 else work.iloc[0]
        latest_val = safe_float(latest[close_col])
        month_val = safe_float(month_ago[close_col])
        monthly_change = None
        if latest_val is not None and month_val not in (None, 0):
            monthly_change = round((latest_val - month_val) / month_val * 100, 4)
        return {
            "value": latest_val,
            "date": str(latest[date_col])[:10],
            "monthly_change_pct": monthly_change,
            "source": "akshare/index_global_hist_em/美元指数",
            "provider": self.name,
        }

    _BROAD_ETF_FLOW_SYMBOLS = (
        ("510300", "sh"),
        ("510500", "sh"),
        ("159915", "sz"),
        ("512100", "sh"),
        ("588000", "sh"),
        ("510050", "sh"),
    )

    @provider_cached(lambda self, weeks=4, **_: f"etf_flow:{max(1, min(int(weeks or 4), 12))}")
    def get_etf_fund_flow(self, *, weeks: int = 4) -> dict[str, Any]:
        weeks = max(1, min(int(weeks or 4), 12))
        trading_days = weeks * 5
        ak = _import_akshare()
        etf_today_total = None
        try:
            etf_df = self._load_etf_spot()
            inflow_col = next((c for c in etf_df.columns if "主力净流入" in str(c) and "净额" in str(c)), None)
            if inflow_col:
                values = pd.to_numeric(etf_df[inflow_col], errors="coerce").dropna().tolist()
                if values:
                    etf_today_total = round(sum(values), 2)
        except Exception as exc:
            logger.warning("etf spot inflow failed: %s", exc)
        broad_flows: list[dict[str, Any]] = []
        broad_sum = 0.0
        broad_count = 0
        for code, market in self._BROAD_ETF_FLOW_SYMBOLS:
            try:
                flow_df = retry_call(lambda c=code, m=market: ak.stock_individual_fund_flow(stock=c, market=m))
                if flow_df is None or flow_df.empty:
                    continue
                net_col = next((c for c in flow_df.columns if "主力净流入" in str(c) and "净额" in str(c)), None)
                if net_col is None:
                    continue
                recent = flow_df.tail(trading_days)
                values = pd.to_numeric(recent[net_col], errors="coerce").dropna().tolist()
                if not values:
                    continue
                total = round(sum(values), 2)
                broad_flows.append({"symbol": code, "market": market.upper(), "main_net_inflow_sum": total})
                broad_sum += total
                broad_count += 1
            except Exception as exc:
                logger.warning("etf fund flow %s failed: %s", code, exc)
        market_daily: list[dict[str, Any]] = []
        market_sum = None
        try:
            market_df = retry_call(lambda: ak.stock_market_fund_flow())
            net_col = next((c for c in market_df.columns if "主力净流入" in str(c) and "净额" in str(c)), None)
            date_col = next((c for c in market_df.columns if "日期" in str(c)), market_df.columns[0])
            if net_col is not None:
                recent = market_df.tail(trading_days)
                values = pd.to_numeric(recent[net_col], errors="coerce").dropna().tolist()
                if values:
                    market_sum = round(sum(values), 2)
                for _, row in recent.iterrows():
                    market_daily.append(
                        {
                            "date": str(row.get(date_col))[:10],
                            "main_net_inflow": safe_float(row.get(net_col)),
                        }
                    )
        except Exception as exc:
            logger.warning("market fund flow failed: %s", exc)
        if etf_today_total is None and broad_count == 0 and market_sum is None:
            raise ValueError("etf fund flow unavailable")
        return {
            "weeks": weeks,
            "trading_days": trading_days,
            "etf_main_net_inflow_today": etf_today_total,
            "broad_etf_main_net_inflow_sum": round(broad_sum, 2) if broad_count else None,
            "broad_etf_count": broad_count,
            "broad_etf_flows": broad_flows,
            "market_main_net_inflow_sum": market_sum,
            "market_main_net_inflow_daily": market_daily,
            "source": "akshare/fund_etf_spot_em+stock_individual_fund_flow+stock_market_fund_flow",
            "provider": self.name,
            "as_of_date": today_str(),
            "note": "4w sum uses broad ETF basket; market series is whole-market main-flow reference; "
            "eastmoney modeled main-flow not exchange official subscription/redemption",
        }

    @provider_cached(
        lambda self, sector, window_years=5, consecutive_days=5, high_percentile=90.0, **_: (
            f"sector_liq:{(sector or '').strip()}:"
            f"{max(1, min(int(window_years or 5), 10))}:"
            f"{max(1, min(int(consecutive_days or 5), 20))}:"
            f"{max(50.0, min(float(high_percentile or 90.0), 99.0))}"
        )
    )
    def get_sector_liquidity(
        self,
        sector: str,
        *,
        window_years: int = 5,
        consecutive_days: int = 5,
        high_percentile: float = 90.0,
    ) -> dict[str, Any]:
        window_years = max(1, min(int(window_years or 5), 10))
        consecutive_days = max(1, min(int(consecutive_days or 5), 20))
        high_percentile = max(50.0, min(float(high_percentile or 90.0), 99.0))
        ak = _import_akshare()
        sector_name = (sector or "").strip()
        if not sector_name:
            raise ValueError("sector is required")
        boards = retry_call(lambda: ak.stock_board_industry_name_em())
        if boards is None or boards.empty:
            raise ValueError("sector board unavailable")
        name_col = next((c for c in boards.columns if "板块" in str(c) or "名称" in str(c)), boards.columns[1])
        amount_col = next((c for c in boards.columns if "成交额" in str(c) or "总金额" in str(c)), None)
        if amount_col is None:
            raise ValueError("sector amount column missing")
        match = boards[boards[name_col].astype(str).str.contains(sector_name, na=False)]
        if match.empty:
            match = boards[boards[name_col].astype(str) == sector_name]
        if match.empty:
            raise ValueError(f"sector not found: {sector}")
        board_name = str(match.iloc[0][name_col])
        sector_amount_today = safe_float(match.iloc[0].get(amount_col))
        try:
            spot_df = self._load_cn_a_spot()
            total_col = next((c for c in spot_df.columns if "成交额" in str(c)), None)
            total_amount_today = None
            if total_col is not None:
                total_amount_today = safe_float(pd.to_numeric(spot_df[total_col], errors="coerce").sum())
        except Exception as exc:
            logger.warning("market total amount failed: %s", exc)
            total_amount_today = None
        ratio_today = None
        if sector_amount_today is not None and total_amount_today not in (None, 0):
            ratio_today = round(sector_amount_today / total_amount_today * 100, 4)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365 * window_years + 30)).strftime("%Y%m%d")
        sector_hist = retry_call(
            lambda: ak.stock_board_industry_hist_em(
                symbol=board_name,
                start_date=start_date,
                end_date=end_date,
                period="日k",
                adjust="",
            )
        )
        market_hist, market_source = fetch_index_daily_df(
            ak,
            index_code="000985",
            start_date=start_date,
            end_date=end_date,
            need_amount=True,
        )
        if sector_hist is None or sector_hist.empty or market_hist is None or market_hist.empty:
            raise ValueError("sector liquidity history unavailable")
        sec_date_col = next((c for c in sector_hist.columns if "日期" in str(c)), sector_hist.columns[0])
        sec_amount_col = next((c for c in sector_hist.columns if "成交额" in str(c)), None)
        mkt_date_col = next((c for c in market_hist.columns if "日期" in str(c)), market_hist.columns[0])
        mkt_amount_col = next(
            (c for c in market_hist.columns if "成交额" in str(c) or "amount" in str(c).lower()),
            None,
        )
        if sec_amount_col is None or mkt_amount_col is None:
            raise ValueError("sector liquidity amount columns missing")
        sec_work = sector_hist[[sec_date_col, sec_amount_col]].copy()
        sec_work.columns = ["date", "sector_amount"]
        mkt_work = market_hist[[mkt_date_col, mkt_amount_col]].copy()
        mkt_work.columns = ["date", "market_amount"]
        sec_work["date"] = pd.to_datetime(sec_work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        mkt_work["date"] = pd.to_datetime(mkt_work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        merged = sec_work.merge(mkt_work, on="date", how="inner")
        merged["sector_amount"] = pd.to_numeric(merged["sector_amount"], errors="coerce")
        merged["market_amount"] = pd.to_numeric(merged["market_amount"], errors="coerce")
        merged = merged.dropna()
        merged = merged[merged["market_amount"] > 0]
        if merged.empty:
            raise ValueError("sector liquidity ratio series empty")
        ratios = (merged["sector_amount"] / merged["market_amount"] * 100).tolist()
        latest_ratio = ratios[-1]
        percentile = percentile_of(latest_ratio, ratios)
        threshold = None
        if len(ratios) >= 10:
            sorted_ratios = sorted(ratios)
            idx = int(round((high_percentile / 100) * (len(sorted_ratios) - 1)))
            threshold = sorted_ratios[max(0, min(idx, len(sorted_ratios) - 1))]
        high_streak = 0
        if threshold is not None:
            for ratio in reversed(ratios):
                if ratio >= threshold:
                    high_streak += 1
                else:
                    break
        return {
            "sector": board_name,
            "turnover_ratio_pct_latest": round(latest_ratio, 4),
            "turnover_ratio_percentile": percentile,
            "percentile_window_years": window_years,
            "high_percentile_threshold": high_percentile,
            "high_percentile_value_pct": threshold,
            "high_percentile_consecutive_days": high_streak,
            "ban_sector_etf": high_streak >= consecutive_days and percentile is not None and percentile >= high_percentile,
            "ratio_today_spot_pct": ratio_today,
            "sample_size": len(ratios),
            "latest_date": merged.iloc[-1]["date"],
            "source": f"akshare/stock_board_industry_hist_em+{market_source.split('/', 1)[-1]}",
            "provider": self.name,
            "as_of_date": today_str(),
        }

    def get_etf_snapshot(self, symbol: str) -> dict[str, Any]:
        df = self._load_etf_spot()
        code = str(symbol).strip()
        match = df[df["代码"].astype(str) == code]
        if match.empty:
            raise ValueError(f"ETF not found: {symbol}")
        row = match.iloc[0].to_dict()
        return self._etf_row_to_snapshot(row)

    def _etf_row_to_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        code = str(pick_column(row, "代码", "symbol") or "")
        premium = safe_float(pick_column(row, "基金折价率", "IOPV实时估值", "premium_rate"))
        return {
            "symbol": code,
            "name": str(pick_column(row, "名称", "name") or ""),
            "price": safe_float(pick_column(row, "最新价", "price")),
            "change_pct": safe_float(pick_column(row, "涨跌幅", "change_pct")),
            "amount": safe_float(pick_column(row, "成交额", "amount")),
            "volume": safe_float(pick_column(row, "成交量", "volume")),
            "turnover_rate": safe_float(pick_column(row, "换手率", "turnover_rate")),
            "market_cap": safe_float(pick_column(row, "总市值", "market_cap")),
            "premium_rate": premium,
            "source": "akshare/fund_etf_spot_em",
            "provider": self.name,
            "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        }

    def screen_etfs(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort_by: str = "amount",
        limit: int = 50,
    ) -> dict[str, Any]:
        filters = filters or {}
        limit = max(1, min(int(limit or 50), 200))
        df = self._load_etf_spot()
        rows = [self._etf_row_to_snapshot(row.to_dict()) for _, row in df.iterrows()]
        filtered = [row for row in rows if self._match_etf_filters(row, filters)]
        field_map = {"amount": "amount", "turnover_rate": "turnover_rate", "change_pct": "change_pct", "premium_rate": "premium_rate"}
        field = field_map.get((sort_by or "amount").strip().lower(), "amount")
        filtered.sort(key=lambda item: abs(item.get(field) or 0), reverse=True)
        return {
            "matched_count": len(filtered),
            "filters": filters,
            "etfs": filtered[:limit],
            "source": self.source,
            "provider": self.name,
            "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        }

    def _match_etf_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        name = row.get("name") or ""
        if filters.get("exclude_leveraged") and ("杠杆" in name or "两倍" in name or "2倍" in name):
            return False
        checks = [
            ("amount_min", row.get("amount"), lambda v, t: v is not None and v >= t),
            ("turnover_rate_min", row.get("turnover_rate"), lambda v, t: v is not None and v >= t),
            ("premium_rate_min", row.get("premium_rate"), lambda v, t: v is not None and v >= t),
            ("premium_rate_max", row.get("premium_rate"), lambda v, t: v is not None and v <= t),
            ("change_pct_min", row.get("change_pct"), lambda v, t: v is not None and v >= t),
            ("change_pct_max", row.get("change_pct"), lambda v, t: v is not None and v <= t),
        ]
        for key, actual, fn in checks:
            target = filters.get(key)
            if target is None:
                continue
            threshold = safe_float(target)
            if threshold is None or not fn(actual, threshold):
                return False
        keywords = filters.get("name_keywords")
        if keywords:
            text = name.lower()
            if not any(str(k).lower() in text for k in keywords):
                return False
        return True

    def get_chip_distribution(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        if market_key != "CN_A":
            raise ValueError("chip distribution currently supports CN_A only")
        ak = _import_akshare()
        adjust = ""
        df = retry_call(lambda: ak.stock_cyq_em(symbol=code, adjust=adjust))
        if df is None or df.empty:
            raise ValueError(f"chip distribution unavailable: {symbol}")
        latest = df.iloc[-1].to_dict()
        date_val = pick_column(latest, "日期", "date")
        return {
            "symbol": code,
            "market": market_key,
            "date": str(date_val)[:10] if date_val is not None else today_str(),
            "profit_ratio_pct": safe_float(pick_column(latest, "获利比例")),
            "avg_cost": safe_float(pick_column(latest, "平均成本")),
            "cost_90_low": safe_float(pick_column(latest, "90成本-低")),
            "cost_90_high": safe_float(pick_column(latest, "90成本-高")),
            "concentration_90": safe_float(pick_column(latest, "90集中度")),
            "concentration_70": safe_float(pick_column(latest, "70集中度")),
            "source": "akshare/stock_cyq_em",
            "provider": self.name,
            "as_of_date": str(date_val)[:10] if date_val is not None else today_str(),
        }

    def search_announcements(self, symbol: str, *, limit: int = 10, market: str | None = None) -> dict[str, Any]:
        code, market_key = parse_symbol(symbol, market)
        ak = _import_akshare()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _append(item: dict[str, Any]) -> None:
            key = f"{item.get('title')}::{item.get('date')}"
            if key in seen:
                return
            seen.add(key)
            items.append(item)

        if market_key == "HK":
            try:
                news_df = retry_call(lambda: ak.stock_news_em(symbol=code))
                if news_df is not None and not news_df.empty:
                    for _, row in news_df.head(limit).iterrows():
                        item = row.to_dict()
                        _append(
                            {
                                "title": str(pick_column(item, "新闻标题", "title") or ""),
                                "date": str(pick_column(item, "发布时间", "date") or "")[:19],
                                "url": str(pick_column(item, "新闻链接", "url") or ""),
                                "source": "eastmoney_news_hk",
                                "category": "news",
                            }
                        )
            except Exception as exc:
                logger.warning("hk stock news failed for %s: %s", code, exc)
            return {
                "symbol": code,
                "market": market_key,
                "items": items[:limit],
                "source": "akshare/stock_news_em",
                "provider": self.name,
                "as_of_date": datetime.now().strftime("%Y-%m-%d"),
                "note": "HK uses news feed; verify key figures via hkex PDF web_fetch",
            }

        try:
            cn_df = retry_call(
                lambda: ak.stock_zh_a_disclosure_report_cninfo(symbol=code, category="重大事项")
            )
            if cn_df is not None and not cn_df.empty:
                for _, row in cn_df.head(limit).iterrows():
                    item = row.to_dict()
                    _append(
                        {
                            "title": str(pick_column(item, "公告标题", "title") or ""),
                            "date": str(pick_column(item, "公告时间", "date") or "")[:19],
                            "url": str(pick_column(item, "公告链接", "url", "链接") or ""),
                            "source": "cninfo",
                            "category": str(pick_column(item, "公告类型", "category") or ""),
                        }
                    )
        except Exception as exc:
            logger.warning("cninfo disclosure failed for %s: %s", code, exc)
        if len(items) < limit:
            try:
                news_df = retry_call(lambda: ak.stock_news_em(symbol=code))
                if news_df is not None and not news_df.empty:
                    for _, row in news_df.head(limit).iterrows():
                        item = row.to_dict()
                        _append(
                            {
                                "title": str(pick_column(item, "新闻标题", "title") or ""),
                                "date": str(pick_column(item, "发布时间", "date") or "")[:19],
                                "url": str(pick_column(item, "新闻链接", "url") or ""),
                                "source": "eastmoney_news",
                                "category": "news",
                            }
                        )
            except Exception as exc:
                logger.warning("stock news failed for %s: %s", code, exc)
        return {
            "symbol": code,
            "market": market_key,
            "items": items[:limit],
            "source": "cninfo+akshare_news",
            "provider": self.name,
            "as_of_date": datetime.now().strftime("%Y-%m-%d"),
            "note": "重大财务数字须 web_fetch 巨潮 PDF 核对",
        }

    @provider_cached(
        lambda self, index="000300", days=20, **_: (
            f"volatility:{resolve_index(index)}:{max(5, min(int(days or 20), 120))}"
        )
    )
    def get_market_volatility(self, *, index: str = "000300", days: int = 20) -> dict[str, Any]:
        days = max(5, min(int(days or 20), 120))
        ak = _import_akshare()
        resolved = resolve_index(index)
        index_code = _index_code_digits(resolved, default="000300" if resolved not in {"000985", "csi_all"} else "000985")
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 40)).strftime("%Y%m%d")
        df, daily_source = fetch_index_daily_df(
            ak,
            index_code=index_code,
            start_date=start_date,
            end_date=end_date,
            need_amount=False,
        )
        if df is None or df.empty:
            raise ValueError("index volatility data unavailable")
        date_col = "日期" if "日期" in df.columns else df.columns[0]
        high_col = next((c for c in df.columns if str(c) in {"最高", "high"}), None)
        low_col = next((c for c in df.columns if str(c) in {"最低", "low"}), None)
        close_col = next((c for c in df.columns if "收盘" in str(c)), df.columns[-2])
        if high_col is None or low_col is None:
            raise ValueError("index OHLC columns missing")
        frame = df.copy()
        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        frame = frame.dropna(subset=[date_col]).sort_values(date_col).tail(days + 1)
        daily_ranges: list[dict[str, Any]] = []
        prev_close = None
        consecutive_above_3 = 0
        max_consecutive_above_3 = 0
        for _, row in frame.iterrows():
            high = safe_float(row.get(high_col))
            low = safe_float(row.get(low_col))
            close = safe_float(row.get(close_col))
            base = prev_close or close
            range_pct = None
            if high is not None and low is not None and base and base > 0:
                range_pct = round((high - low) / base * 100, 4)
            date_val = row[date_col]
            date_text = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
            if range_pct is not None and prev_close is not None:
                daily_ranges.append({"date": date_text, "daily_range_pct": range_pct})
                if range_pct > 3.0:
                    consecutive_above_3 += 1
                    max_consecutive_above_3 = max(max_consecutive_above_3, consecutive_above_3)
                else:
                    consecutive_above_3 = 0
            if close is not None:
                prev_close = close
        latest_ranges = [
            item["daily_range_pct"] for item in daily_ranges[-days:] if item.get("daily_range_pct") is not None
        ]
        avg_range = round(sum(latest_ranges) / len(latest_ranges), 4) if latest_ranges else None
        latest_range = daily_ranges[-1]["daily_range_pct"] if daily_ranges else None
        vix_latest = None
        vix_percentile = None
        vix_date = None
        try:
            spot_df = retry_call(lambda: ak.index_global_spot_em())
            if spot_df is not None and not spot_df.empty:
                name_col = "名称" if "名称" in spot_df.columns else spot_df.columns[0]
                match = spot_df[spot_df[name_col].astype(str).str.upper().str.contains("VIX", na=False)]
                if not match.empty:
                    row = match.iloc[0].to_dict()
                    vix_latest = safe_float(pick_column(row, "最新价", "price", "close"))
        except Exception as exc:
            logger.warning("vix spot failed: %s", exc)
        try:
            hist_df = retry_call(lambda: ak.index_global_hist_em(symbol="VIX"))
            if hist_df is not None and not hist_df.empty:
                close_col_v = next(
                    (c for c in hist_df.columns if "收盘" in str(c) or str(c).lower() == "close"),
                    None,
                )
                date_col_v = "日期" if "日期" in hist_df.columns else hist_df.columns[0]
                if close_col_v:
                    series = pd.to_numeric(hist_df[close_col_v], errors="coerce").dropna().tolist()
                    if vix_latest is None and series:
                        vix_latest = series[-1]
                    if vix_latest and series:
                        vix_percentile = percentile_of(vix_latest, series[-1250:])
                    latest = hist_df.iloc[-1]
                    vix_date = str(latest.get(date_col_v))[:10]
        except Exception as exc:
            logger.warning("vix history failed: %s", exc)
        cn_qvix = None
        try:
            qvix_df = retry_call(lambda: ak.index_option_300index_qvix())
            if qvix_df is not None and not qvix_df.empty:
                val_col = qvix_df.columns[-1]
                cn_qvix = safe_float(qvix_df.iloc[-1].get(val_col))
        except Exception as exc:
            logger.warning("cn qvix failed: %s", exc)
        return {
            "index": index,
            "resolved_index": resolved,
            "days": days,
            "daily_range_pct_latest": latest_range,
            "daily_range_pct_avg": avg_range,
            "consecutive_days_range_above_3pct": max_consecutive_above_3,
            "daily_ranges": daily_ranges[-min(days, 10) :],
            "vix_latest": vix_latest,
            "vix_percentile_5y": vix_percentile,
            "vix_date": vix_date,
            "cn_qvix_300": cn_qvix,
            "source": f"{daily_source}+index_global_hist_em+index_option_300index_qvix",
            "provider": self.name,
            "as_of_date": daily_ranges[-1]["date"] if daily_ranges else today_str(),
            "note": "daily_range=(high-low)/prev_close; VIX from global index when available",
        }

    def _compute_margin_percentile(self, ak: Any, *, window_years: int = 5) -> dict[str, Any]:
        df = retry_call(lambda: ak.macro_china_market_margin_sh())
        if df is None or df.empty:
            return {}
        date_col = df.columns[0]
        financing_col = None
        total_col = None
        for col in df.columns:
            text = str(col)
            if "融资融券余额" in text:
                total_col = col
            elif "融资余额" in text:
                financing_col = col
        if financing_col is None and len(df.columns) > 2:
            financing_col = df.columns[2]
        if total_col is None:
            total_col = df.columns[-1]
        frame = df.copy()
        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        frame = frame.dropna(subset=[date_col]).sort_values(date_col)
        cutoff = datetime.now() - timedelta(days=365 * max(window_years, 1))
        window = frame[frame[date_col] >= cutoff]
        if window.empty:
            window = frame.tail(max(250, window_years * 50))
        financing_series = pd.to_numeric(window[financing_col], errors="coerce").dropna().tolist()
        latest = frame.iloc[-1]
        latest_financing = safe_float(latest[financing_col])
        latest_total = safe_float(latest[total_col])
        latest_date = latest[date_col]
        percentile = percentile_of(latest_financing, financing_series) if latest_financing and financing_series else None
        return {
            "financing_balance": latest_financing,
            "margin_total_balance": latest_total,
            "financing_balance_percentile": percentile,
            "percentile_window_years": window_years,
            "sample_size": len(financing_series),
            "latest_date": latest_date.strftime("%Y-%m-%d") if hasattr(latest_date, "strftime") else str(latest_date)[:10],
        }

    @provider_cached(
        lambda self, days=5, window_years=5, **_: (
            f"sentiment:{max(1, min(int(days or 5), 60))}:{max(1, min(int(window_years or 5), 10))}"
        )
    )
    def get_market_sentiment(self, *, days: int = 5, window_years: int = 5) -> dict[str, Any]:
        days = max(1, min(int(days or 5), 60))
        window_years = max(1, min(int(window_years or 5), 10))
        ak = _import_akshare()
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 15)).strftime("%Y%m%d")
        northbound: list[dict[str, Any]] = []
        try:
            df = retry_call(lambda: ak.stock_hsgt_hist_em(symbol="北向资金", start_date=start, end_date=end))
            if df is not None and not df.empty:
                date_col = "日期" if "日期" in df.columns else df.columns[0]
                net_col = None
                for col in df.columns:
                    text = str(col)
                    if "净流入" in text or "净买" in text or "当日资金" in text:
                        net_col = col
                        break
                if net_col is None and len(df.columns) > 1:
                    net_col = df.columns[1]
                for _, row in df.tail(days).iterrows():
                    northbound.append(
                        {
                            "date": str(row[date_col])[:10],
                            "net_inflow": safe_float(row.get(net_col)),
                        }
                    )
        except Exception as exc:
            logger.warning("northbound flow failed: %s", exc)
        margin: dict[str, Any] = {}
        try:
            margin.update(self._compute_margin_percentile(ak, window_years=window_years))
        except Exception as exc:
            logger.warning("margin percentile failed: %s", exc)
        try:
            sse_df = retry_call(lambda: ak.stock_margin_sse())
            if sse_df is not None and not sse_df.empty:
                latest = sse_df.iloc[-1].to_dict()
                margin["sse_financing_balance"] = safe_float(pick_column(latest, "融资余额"))
                margin["sse_securities_balance"] = safe_float(pick_column(latest, "融券余额"))
                margin["sse_date"] = str(pick_column(latest, "信用交易日期", "日期"))[:10]
        except Exception as exc:
            logger.warning("sse margin failed: %s", exc)
        try:
            sz_df = retry_call(lambda: ak.stock_margin_szse())
            if sz_df is not None and not sz_df.empty:
                latest = sz_df.iloc[-1].to_dict()
                margin["szse_financing_balance"] = safe_float(pick_column(latest, "融资余额"))
                margin["szse_securities_balance"] = safe_float(pick_column(latest, "融券余额"))
                margin["szse_date"] = str(pick_column(latest, "信用交易日期", "日期"))[:10]
        except Exception as exc:
            logger.warning("szse margin failed: %s", exc)
        if not northbound and not margin:
            raise ValueError("market sentiment unavailable")
        latest_north = northbound[-1] if northbound else {}
        as_of = (
            latest_north.get("date")
            or margin.get("latest_date")
            or margin.get("sse_date")
            or today_str()
        )
        return {
            "days": days,
            "northbound_flow": northbound,
            "northbound_latest_net_inflow": latest_north.get("net_inflow"),
            "northbound_latest_date": latest_north.get("date"),
            "margin": margin,
            "financing_balance_percentile": margin.get("financing_balance_percentile"),
            "percentile_window_years": window_years,
            "source": "akshare/stock_hsgt_hist_em+macro_china_market_margin_sh",
            "provider": self.name,
            "as_of_date": as_of,
        }

    @provider_cached(
        lambda self, symbols=None, window_years=10, include_technicals=True, **_: (
            f"overseas:{max(5, min(int(window_years or 10), 10))}:{bool(include_technicals)}:"
            f"{','.join(sorted(str(item).strip() for item in (symbols or DEFAULT_QDII_SYMBOLS) if str(item).strip()))}"
        )
    )
    def get_overseas_market_snapshot(
        self,
        *,
        symbols: list[str] | None = None,
        window_years: int = 10,
        include_technicals: bool = True,
    ) -> dict[str, Any]:
        window_years = max(5, min(int(window_years or 10), 10))
        codes = [str(item).strip() for item in (symbols or DEFAULT_QDII_SYMBOLS) if str(item).strip()]
        index_valuations: dict[str, dict[str, Any]] = {}
        index_errors: dict[str, str] = {}
        for code in OVERSEAS_INDEX_CODES:
            try:
                index_valuations[code] = self.get_index_valuation(code, window_years=window_years)
            except Exception as exc:
                index_errors[code] = str(exc)[:160]
        cross_market = None
        cross_market_error = None
        try:
            cross_market = self.get_cross_market_indicators()
        except Exception as exc:
            cross_market_error = str(exc)[:160]
        relative_value = build_overseas_relative_value(index_valuations)
        ak = _import_akshare()
        eps_growth_outlook = build_eps_growth_outlook(ak)
        for candidate in relative_value.get("path_two_candidates") or []:
            code = candidate.get("index")
            outlook = (eps_growth_outlook.get("outlook_by_index") or {}).get(code) or {}
            if outlook.get("available"):
                candidate["eps_growth_outlook"] = outlook
            else:
                candidate["eps_growth_outlook"] = unavailable_payload(
                    reason=str(outlook.get("reason") or "eps_growth_unavailable"),
                    web_hint="web_fetch broker 12M EPS consensus if required",
                )
        purchase_df = None
        try:
            purchase_df = retry_call(lambda: ak.fund_purchase_em())
        except Exception as exc:
            logger.warning("fund purchase table failed: %s", exc)
        qdii_etfs: list[dict[str, Any]] = []
        for symbol in codes:
            item: dict[str, Any] = {"symbol": symbol}
            try:
                item.update(self.get_etf_snapshot(symbol))
            except Exception as exc:
                item["error"] = str(exc)[:160]
                qdii_etfs.append(item)
                continue
            try:
                item.update(fetch_qdii_fund_meta(ak, symbol, purchase_df=purchase_df))
            except Exception as exc:
                item["fund_meta_error"] = str(exc)[:120]
            if include_technicals:
                try:
                    bars_payload = self.get_bars(symbol, freq="1d", adjust="none", limit=260)
                    item["technical"] = compute_etf_entry_technicals(bars_payload.get("bars") or [])
                except Exception as exc:
                    item["technical"] = {"available": False, "reason": str(exc)[:120]}
            premium = item.get("premium_rate")
            item["premium_ok_for_entry"] = premium is None or abs(premium) <= 3.0
            item["subscription_action"] = build_qdii_subscription_action(
                subscription_open=item.get("subscription_open"),
                premium_rate=premium,
            )
            qdii_etfs.append(item)
        return {
            "as_of_date": today_str(),
            "window_years": window_years,
            "cross_market": cross_market,
            "cross_market_error": cross_market_error,
            "index_valuations": index_valuations,
            "index_errors": index_errors or None,
            "relative_value": relative_value,
            "eps_growth_outlook": eps_growth_outlook,
            "qdii_etfs": qdii_etfs,
            "source": "akshare/index_global+etf_spot+bars+fund_purchase_em+fund_overview_em",
            "provider": self.name,
        }
