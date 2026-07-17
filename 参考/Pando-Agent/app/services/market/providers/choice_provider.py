import logging
from datetime import datetime, timedelta
from typing import Any
from ..schemes import CHOICE_MACRO_EDB, INDEX_WIND_CODES, resolve_index
from ..utils import normalize_date, parse_symbol, percentile_of, safe_float, to_wind_code, today_str

logger = logging.getLogger(__name__)
_CHOICE_STARTED = False


def _ensure_choice(username: str, password: str, activate_code: str = ""):
    global _CHOICE_STARTED
    try:
        from EmQuantAPI import c
    except ImportError as exc:
        raise NotImplementedError(
            "EmQuantAPI not installed. Install Choice terminal SDK and log in with a valid account."
        ) from exc
    if not _CHOICE_STARTED:
        options = "ForceLogin=1"
        if activate_code.strip():
            options = f"ActivateCode={activate_code.strip()},{options}"
        ret = c.start(options, "", username, password)
        if ret.ErrorCode != 0:
            raise RuntimeError(f"Choice login failed: {ret.ErrorMsg}")
        _CHOICE_STARTED = True
    return c


def _choice_css_row(c: Any, codes: list[str], indicators: str) -> dict[str, float | None]:
    data = c.css(codes, indicators, "Type=1")
    if data.ErrorCode != 0:
        raise RuntimeError(f"Choice css failed: {data.ErrorMsg}")
    result: dict[str, float | None] = {}
    for code in codes:
        for field in indicators.split(","):
            key = field.strip()
            val = data.Data.get(code, {}).get(key)
            result[key.lower()] = safe_float(val)
    return result


class ChoiceMarketProvider:
    name = "choice"
    source = "choice_emquant"

    def __init__(self, username: str, password: str, activate_code: str = "") -> None:
        self._c = _ensure_choice(username, password, activate_code)

    def get_realtime_quote(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        wind_code, market_key = to_wind_code(symbol, market)
        fields = _choice_css_row(self._c, [wind_code], "NOW,PE,PB,TURN,AMOUNT,TOTALMV,PCTCHANGE")
        return {
            "symbol": parse_symbol(symbol, market)[0],
            "market": market_key,
            "price": fields.get("now"),
            "change_pct": fields.get("pctchange"),
            "turnover_rate": fields.get("turn"),
            "pe_ttm": fields.get("pe"),
            "pb": fields.get("pb"),
            "market_cap": fields.get("totalmv"),
            "amount": fields.get("amount"),
            "delayed": False,
            "source": self.source,
            "provider": self.name,
            "as_of_date": today_str(),
            "choice_code": wind_code,
        }

    def get_stock_snapshot(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        snapshot = self.get_realtime_quote(symbol, market)
        wind_code, _ = to_wind_code(symbol, market)
        fields = _choice_css_row(
            self._c,
            [wind_code],
            "ROE,GROSSPROFITMARGIN,DEBTTOASSET,NETPROFITGROWTH,OPERATINGREVENUEYOY",
        )
        snapshot.update(
            {
                "roe": fields.get("roe"),
                "gross_margin": fields.get("grossprofitmargin"),
                "debt_ratio": fields.get("debttoasset"),
                "net_profit_yoy": fields.get("netprofitgrowth"),
                "revenue_yoy": fields.get("operatingrevenueyoy"),
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
        wind_code, market_key = to_wind_code(symbol, market)
        end = today_str()
        start = (datetime.now() - timedelta(days=365 * max(years, 1) + 30)).strftime("%Y-%m-%d")
        data = self._c.csd(
            wind_code,
            "ROE,GROSSPROFITMARGIN,DEBTTOASSET,NETPROFITGROWTH,OPERATINGREVENUEYOY",
            start,
            end,
            "Period=2,Ispandas=0",
        )
        if data.ErrorCode != 0:
            raise RuntimeError(f"Choice csd fundamentals failed: {data.ErrorMsg}")
        records: list[dict[str, Any]] = []
        dates = data.Dates or []
        for idx, dt in enumerate(dates):
            item = {"report_date": str(dt)[:10]}
            for key, series in (data.Data or {}).items():
                if idx < len(series):
                    val = safe_float(series[idx])
                    lk = key.lower()
                    if lk == "roe":
                        item["roe"] = val
                    elif "gross" in lk:
                        item["gross_margin"] = val
                    elif "debt" in lk:
                        item["debt_ratio"] = val
                    elif "netprofit" in lk:
                        item["net_profit_yoy"] = val
                    elif "operating" in lk or "revenue" in lk:
                        item["revenue_yoy"] = val
            records.append(item)
        records = [r for r in records if any(r.get(k) is not None for k in ("roe", "gross_margin"))]
        if years > 0:
            records = records[-years:]
        return {
            "symbol": parse_symbol(symbol, market)[0],
            "market": market_key,
            "years": years,
            "records": records,
            "source": self.source,
            "provider": self.name,
            "as_of_date": records[-1]["report_date"] if records else today_str(),
            "choice_code": wind_code,
        }

    def get_stock_valuation(
        self,
        symbol: str,
        *,
        window_years: int = 5,
        market: str | None = None,
    ) -> dict[str, Any]:
        wind_code, market_key = to_wind_code(symbol, market)
        snapshot = self.get_realtime_quote(symbol, market)
        end = today_str()
        start = (datetime.now() - timedelta(days=365 * max(window_years, 1))).strftime("%Y-%m-%d")
        data = self._c.csd(wind_code, "PE,PB,DIVIDENDYIELD", start, end, "Period=1,Ispandas=0")
        if data.ErrorCode != 0:
            raise RuntimeError(f"Choice csd valuation failed: {data.ErrorMsg}")
        pe_series: list[float] = []
        pe_data = (data.Data or {}).get("PE") or []
        pe_series = [v for v in (safe_float(x) for x in pe_data) if v is not None]
        pe_ttm = snapshot.get("pe_ttm")
        pb = snapshot.get("pb")
        div_data = (data.Data or {}).get("DIVIDENDYIELD") or []
        div_yield = safe_float(div_data[-1]) if div_data else None
        fin = self.get_stock_fundamentals(symbol, years=1, market=market)
        growth = fin["records"][-1].get("net_profit_yoy") if fin.get("records") else None
        peg = round(pe_ttm / growth, 4) if pe_ttm and growth and growth > 0 else None
        return {
            "symbol": parse_symbol(symbol, market)[0],
            "market": market_key,
            "pe_ttm": pe_ttm,
            "pb": pb,
            "pe_percentile": percentile_of(pe_ttm, pe_series) if pe_ttm else None,
            "percentile_window_years": window_years,
            "dividend_yield_pct": div_yield,
            "peg": peg,
            "profit_growth_yoy_pct": growth,
            "source": self.source,
            "provider": self.name,
            "as_of_date": snapshot.get("as_of_date"),
            "choice_code": wind_code,
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
        if freq in {"1m_intraday", "5m_intraday"}:
            raise NotImplementedError("choice intraday bars not implemented")
        wind_code, market_key = to_wind_code(symbol, market)
        end_date = normalize_date(end)
        if start:
            start_date = normalize_date(start)
        else:
            start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        period_map = {"1d": "1", "1w": "2", "1m": "3"}
        adj_map = {"qfq": "1", "hfq": "2", "none": "3"}
        data = self._c.csd(
            wind_code,
            "OPEN,HIGH,LOW,CLOSE,VOLUME,AMOUNT,TURN",
            start_date,
            end_date,
            f"Period={period_map.get(freq, '1')},AdjustFlag={adj_map.get(adjust, '1')},Ispandas=0",
        )
        if data.ErrorCode != 0:
            raise RuntimeError(f"Choice csd bars failed: {data.ErrorMsg}")
        dates = data.Dates or []
        bars: list[dict[str, Any]] = []
        open_s = (data.Data or {}).get("OPEN") or []
        high_s = (data.Data or {}).get("HIGH") or []
        low_s = (data.Data or {}).get("LOW") or []
        close_s = (data.Data or {}).get("CLOSE") or []
        vol_s = (data.Data or {}).get("VOLUME") or []
        amt_s = (data.Data or {}).get("AMOUNT") or []
        turn_s = (data.Data or {}).get("TURN") or []
        for idx, dt in enumerate(dates):
            bars.append(
                {
                    "date": str(dt)[:10],
                    "open": safe_float(open_s[idx]) if idx < len(open_s) else None,
                    "high": safe_float(high_s[idx]) if idx < len(high_s) else None,
                    "low": safe_float(low_s[idx]) if idx < len(low_s) else None,
                    "close": safe_float(close_s[idx]) if idx < len(close_s) else None,
                    "volume": safe_float(vol_s[idx]) if idx < len(vol_s) else None,
                    "amount": safe_float(amt_s[idx]) if idx < len(amt_s) else None,
                    "turnover": safe_float(turn_s[idx]) if idx < len(turn_s) else None,
                }
            )
        if limit is not None and len(bars) > limit:
            bars = bars[-limit:]
        return {
            "symbol": parse_symbol(symbol, market)[0],
            "market": market_key,
            "freq": freq,
            "adjust": adjust,
            "bars": bars,
            "count": len(bars),
            "source": self.source,
            "provider": self.name,
            "as_of_date": bars[-1]["date"] if bars else end_date,
            "choice_code": wind_code,
        }

    def get_index_valuation(self, index: str, *, window_years: int = 5) -> dict[str, Any]:
        wind_code = INDEX_WIND_CODES.get(resolve_index(index), resolve_index(index))
        end = today_str()
        start = (datetime.now() - timedelta(days=365 * max(window_years, 1))).strftime("%Y-%m-%d")
        data = self._c.csd(wind_code, "PE", start, end, "Period=1,Ispandas=0")
        if data.ErrorCode != 0:
            raise RuntimeError(f"Choice csd index pe failed: {data.ErrorMsg}")
        pe_data = (data.Data or {}).get("PE") or []
        pe_series = [v for v in (safe_float(x) for x in pe_data) if v is not None]
        latest_pe = pe_series[-1] if pe_series else None
        dates = data.Dates or []
        latest_date = str(dates[-1])[:10] if dates else end
        return {
            "index": index,
            "index_name": wind_code,
            "pe_ttm": latest_pe,
            "pe_percentile": percentile_of(latest_pe, pe_series) if latest_pe else None,
            "percentile_window_years": window_years,
            "sample_size": len(pe_series),
            "latest_date": latest_date,
            "source": self.source,
            "provider": self.name,
            "choice_code": wind_code,
        }

    def get_macro_rate(self, indicator: str = "cn_10y") -> dict[str, Any]:
        indicator = (indicator or "cn_10y").strip().lower()
        edb_code = CHOICE_MACRO_EDB.get(indicator)
        if not edb_code:
            raise NotImplementedError(f"choice macro indicator not mapped: {indicator}")
        end = today_str()
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        data = self._c.edb(edb_code, start, end)
        if data.ErrorCode != 0:
            raise RuntimeError(f"Choice edb {indicator} failed: {data.ErrorMsg}")
        dates = data.Dates or []
        values = (data.Data or {}).get(edb_code) or []
        value = safe_float(values[-1]) if values else None
        date_val = str(dates[-1])[:10] if dates else end
        return {
            "indicator": indicator,
            "value_pct": value,
            "date": date_val,
            "source": f"{self.source}/edb/{edb_code}",
            "provider": self.name,
        }

    def screen_stocks(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("use akshare/pywencai for full-market screen")

    def get_etf_snapshot(self, symbol: str) -> dict[str, Any]:
        wind_code, _ = to_wind_code(symbol, "CN_A")
        fields = _choice_css_row(self._c, [wind_code], "NOW,PCTCHANGE,AMOUNT,TURN,PREMIUMRATE")
        return {
            "symbol": str(symbol).strip(),
            "name": wind_code,
            "price": fields.get("now"),
            "change_pct": fields.get("pctchange"),
            "amount": fields.get("amount"),
            "turnover_rate": fields.get("turn"),
            "premium_rate": fields.get("premiumrate"),
            "source": self.source,
            "provider": self.name,
            "as_of_date": today_str(),
        }

    def search_announcements(self, symbol: str, *, limit: int = 10) -> dict[str, Any]:
        raise NotImplementedError("use akshare cninfo for announcements")

    def get_chip_distribution(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        raise NotImplementedError("use akshare stock_cyq_em for chip distribution")

    def get_market_sentiment(self, *, days: int = 5) -> dict[str, Any]:
        raise NotImplementedError("use akshare provider for market sentiment")
