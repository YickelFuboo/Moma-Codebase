import logging
from datetime import datetime, timedelta
from typing import Any
from ..schemes import INDEX_WIND_CODES, WIND_CN_10Y_EDB, WIND_MACRO_EDB, resolve_index
from ..utils import normalize_date, parse_symbol, percentile_of, safe_float, to_wind_code, today_str

logger = logging.getLogger(__name__)
_WIND_STARTED = False


def _ensure_wind():
    global _WIND_STARTED
    try:
        from WindPy import w
    except ImportError as exc:
        raise NotImplementedError(
            "WindPy not installed. Install Wind terminal and WindPy, then ensure Wind client is logged in."
        ) from exc
    if not _WIND_STARTED:
        ret = w.start()
        if getattr(ret, "ErrorCode", -1) != 0:
            raise RuntimeError(f"Wind start failed: {getattr(ret, 'Data', ret)}")
        _WIND_STARTED = True
    return w


def _wind_error(result: Any, context: str) -> None:
    code = getattr(result, "ErrorCode", 0)
    if code != 0:
        raise RuntimeError(f"Wind {context} failed: code={code} data={getattr(result, 'Data', '')}")


def _wind_snapshot_fields(result: Any) -> dict[str, float | None]:
    fields = getattr(result, "Fields", []) or []
    data = getattr(result, "Data", []) or []
    if not fields or not data:
        return {}
    row = data[0] if data else []
    return {str(fields[i]): safe_float(row[i] if i < len(row) else None) for i in range(len(fields))}


class WindMarketProvider:
    name = "wind"
    source = "wind_windpy"

    def __init__(self) -> None:
        self._w = _ensure_wind()

    def get_realtime_quote(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        wind_code, market_key = to_wind_code(symbol, market)
        result = self._w.wss(
            wind_code,
            "rt_last,pe_ttm,pb_lf,turn,amt,mkt_cap_ard,pct_chg",
            "",
        )
        _wind_error(result, "wss")
        fields = _wind_snapshot_fields(result)
        price = fields.get("RT_LAST") or fields.get("rt_last")
        return {
            "symbol": parse_symbol(symbol, market)[0],
            "market": market_key,
            "price": price,
            "change_pct": fields.get("PCT_CHG") or fields.get("pct_chg"),
            "turnover_rate": fields.get("TURN") or fields.get("turn"),
            "pe_ttm": fields.get("PE_TTM") or fields.get("pe_ttm"),
            "pb": fields.get("PB_LF") or fields.get("pb_lf"),
            "market_cap": fields.get("MKT_CAP_ARD") or fields.get("mkt_cap_ard"),
            "amount": fields.get("AMT") or fields.get("amt"),
            "delayed": False,
            "source": self.source,
            "provider": self.name,
            "as_of_date": today_str(),
            "wind_code": wind_code,
        }

    def get_stock_snapshot(self, symbol: str, market: str | None = None) -> dict[str, Any]:
        snapshot = self.get_realtime_quote(symbol, market)
        wind_code, _ = to_wind_code(symbol, market)
        result = self._w.wss(
            wind_code,
            "roe_ttm2,grossprofitmargin,debttoassets,netprofit_growth,or_ttm_yoy",
            "",
        )
        _wind_error(result, "wss fundamentals")
        fields = _wind_snapshot_fields(result)
        snapshot.update(
            {
                "roe": fields.get("ROE_TTM2") or fields.get("roe_ttm2"),
                "gross_margin": fields.get("GROSSPROFITMARGIN") or fields.get("grossprofitmargin"),
                "debt_ratio": fields.get("DEBTTOASSETS") or fields.get("debttoassets"),
                "net_profit_yoy": fields.get("NETPROFIT_GROWTH") or fields.get("netprofit_growth"),
                "revenue_yoy": fields.get("OR_TTM_YOY") or fields.get("or_ttm_yoy"),
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
        result = self._w.wsd(
            wind_code,
            "roe,grossprofitmargin,debttoassets,netprofit_growth,or_yoy",
            start,
            end,
            "Period=Y;Days=Alldays",
        )
        _wind_error(result, "wsd fundamentals")
        times = getattr(result, "Times", []) or []
        data = getattr(result, "Data", []) or []
        fields = getattr(result, "Fields", []) or []
        records: list[dict[str, Any]] = []
        if times and data:
            for idx, dt in enumerate(times):
                item = {"report_date": str(dt)[:10]}
                for fi, fname in enumerate(fields):
                    if fi < len(data) and idx < len(data[fi]):
                        val = safe_float(data[fi][idx])
                        key = str(fname).lower()
                        if key == "roe":
                            item["roe"] = val
                        elif "gross" in key:
                            item["gross_margin"] = val
                        elif "debt" in key:
                            item["debt_ratio"] = val
                        elif "netprofit" in key:
                            item["net_profit_yoy"] = val
                        elif "or" in key:
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
            "wind_code": wind_code,
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
        result = self._w.wsd(wind_code, "pe_ttm,pb_lf,dvd_yield", start, end, "Days=Alldays")
        _wind_error(result, "wsd valuation")
        pe_series: list[float] = []
        data = getattr(result, "Data", []) or []
        if data and data[0]:
            pe_series = [v for v in (safe_float(x) for x in data[0]) if v is not None]
        pe_ttm = snapshot.get("pe_ttm")
        pb = snapshot.get("pb")
        div_yield = safe_float(data[2][-1]) if len(data) > 2 and data[2] else None
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
            "wind_code": wind_code,
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
            raise NotImplementedError("wind intraday bars use separate barSize params")
        wind_code, market_key = to_wind_code(symbol, market)
        end_date = normalize_date(end)
        if start:
            start_date = normalize_date(start)
        else:
            start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        adj_map = {"qfq": "F", "hfq": "B", "none": ""}
        options = f"PriceAdj={adj_map.get(adjust, 'F')}"
        if freq == "1w":
            options += ";Period=W"
        elif freq == "1m":
            options += ";Period=M"
        result = self._w.wsd(
            wind_code,
            "open,high,low,close,volume,amt,turn",
            start_date,
            end_date,
            options,
        )
        _wind_error(result, "wsd bars")
        times = getattr(result, "Times", []) or []
        data = getattr(result, "Data", []) or []
        bars: list[dict[str, Any]] = []
        for idx, dt in enumerate(times):
            bars.append(
                {
                    "date": str(dt)[:10],
                    "open": safe_float(data[0][idx]) if len(data) > 0 else None,
                    "high": safe_float(data[1][idx]) if len(data) > 1 else None,
                    "low": safe_float(data[2][idx]) if len(data) > 2 else None,
                    "close": safe_float(data[3][idx]) if len(data) > 3 else None,
                    "volume": safe_float(data[4][idx]) if len(data) > 4 else None,
                    "amount": safe_float(data[5][idx]) if len(data) > 5 else None,
                    "turnover": safe_float(data[6][idx]) if len(data) > 6 else None,
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
            "wind_code": wind_code,
        }

    def get_index_valuation(self, index: str, *, window_years: int = 5) -> dict[str, Any]:
        wind_code = INDEX_WIND_CODES.get(resolve_index(index), resolve_index(index))
        end = today_str()
        start = (datetime.now() - timedelta(days=365 * max(window_years, 1))).strftime("%Y-%m-%d")
        result = self._w.wsd(wind_code, "pe_ttm", start, end, "Days=Alldays")
        _wind_error(result, "wsd index pe")
        data = getattr(result, "Data", []) or []
        times = getattr(result, "Times", []) or []
        pe_series = [v for v in (safe_float(x) for x in (data[0] if data else [])) if v is not None]
        latest_pe = pe_series[-1] if pe_series else None
        latest_date = str(times[-1])[:10] if times else end
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
            "wind_code": wind_code,
        }

    def get_macro_rate(self, indicator: str = "cn_10y") -> dict[str, Any]:
        indicator = (indicator or "cn_10y").strip().lower()
        edb_code = WIND_MACRO_EDB.get(indicator, WIND_CN_10Y_EDB if indicator == "cn_10y" else None)
        if not edb_code:
            raise NotImplementedError(f"wind macro indicator not mapped: {indicator}")
        end = today_str()
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        result = self._w.edb(edb_code, start, end)
        _wind_error(result, f"edb {indicator}")
        times = getattr(result, "Times", []) or []
        data = getattr(result, "Data", []) or []
        value = safe_float(data[0][-1]) if data and data[0] else None
        date_val = str(times[-1])[:10] if times else end
        return {
            "indicator": indicator,
            "value_pct": value,
            "date": date_val,
            "source": f"{self.source}/edb/{edb_code}",
            "provider": self.name,
            "note": "Wind EDB series; unmapped indicators fall back to akshare provider chain",
        }

    def screen_stocks(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("use akshare/pywencai for full-market screen; wind supports wset separately")

    def get_etf_snapshot(self, symbol: str) -> dict[str, Any]:
        wind_code, _ = to_wind_code(symbol, "CN_A")
        result = self._w.wss(wind_code, "rt_last,pct_chg,amt,turn,fund_discount_ratio", "")
        _wind_error(result, "wss etf")
        fields = _wind_snapshot_fields(result)
        return {
            "symbol": str(symbol).strip(),
            "name": wind_code,
            "price": fields.get("RT_LAST") or fields.get("rt_last"),
            "change_pct": fields.get("PCT_CHG") or fields.get("pct_chg"),
            "amount": fields.get("AMT") or fields.get("amt"),
            "turnover_rate": fields.get("TURN") or fields.get("turn"),
            "premium_rate": fields.get("FUND_DISCOUNT_RATIO") or fields.get("fund_discount_ratio"),
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
