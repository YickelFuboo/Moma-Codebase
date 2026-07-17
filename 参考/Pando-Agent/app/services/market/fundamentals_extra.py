import logging
from datetime import datetime, timedelta
from typing import Any
import pandas as pd
from .utils import pick_column, safe_float

logger = logging.getLogger(__name__)


def _year_from_date(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(str(text)[:4])
    except ValueError:
        return None


def _volatility_pct(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return round((variance ** 0.5) / abs(mean) * 100, 2)


def fetch_cn_dividend_history(ak: Any, code: str, *, years: int = 5) -> list[dict[str, Any]]:
    try:
        div_df = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
    except Exception as exc:
        logger.warning("cn dividend history failed %s: %s", code, exc)
        return []
    if div_df is None or div_df.empty:
        return []
    by_year: dict[int, float] = {}
    for _, row in div_df.iterrows():
        item = row.to_dict()
        year = _year_from_date(str(pick_column(item, "除权除息日", "公告日期", "派息日") or "")[:10])
        cash = safe_float(pick_column(item, "派息", "现金分红", "每股派息"))
        if year is None or cash is None:
            continue
        by_year[year] = by_year.get(year, 0.0) + cash
    cutoff = max(by_year.keys(), default=0) - years + 1 if by_year else 0
    history = [
        {"year": year, "cash_div_per_share": round(amount, 4)}
        for year, amount in sorted(by_year.items())
        if year >= cutoff
    ]
    return history


def fetch_hk_dividend_history(ak: Any, code: str, *, years: int = 5) -> list[dict[str, Any]]:
    try:
        div_df = ak.stock_hk_dividend_payout_em(symbol=code)
    except Exception as exc:
        logger.warning("hk dividend history failed %s: %s", code, exc)
        return []
    if div_df is None or div_df.empty:
        return []
    by_year: dict[int, float] = {}
    for _, row in div_df.iterrows():
        item = row.to_dict()
        year = _year_from_date(str(pick_column(item, "除权除息日", "公告日期", "派息日", "年度") or "")[:10])
        cash = safe_float(pick_column(item, "派息", "每股派息", "现金分红"))
        if year is None:
            year = _year_from_date(str(pick_column(item, "报告期") or "")[:10])
        if year is None or cash is None:
            continue
        by_year[year] = by_year.get(year, 0.0) + cash
    cutoff = max(by_year.keys(), default=0) - years + 1 if by_year else 0
    return [
        {"year": year, "cash_div_per_share": round(amount, 4)}
        for year, amount in sorted(by_year.items())
        if year >= cutoff
    ]


def fetch_cn_cashflow_records(ak: Any, code: str, *, years: int = 5) -> list[dict[str, Any]]:
    try:
        cf_df = ak.stock_cash_flow_sheet_by_report_em(symbol=code, indicator="按报告期")
    except Exception as exc:
        logger.warning("cn cashflow failed %s: %s", code, exc)
        return []
    if cf_df is None or cf_df.empty:
        return []
    records: list[dict[str, Any]] = []
    for _, row in cf_df.iterrows():
        item = row.to_dict()
        report_date = str(pick_column(item, "报告期", "REPORT_DATE") or "")[:10]
        ocf = safe_float(
            pick_column(
                item,
                "经营活动产生的现金流量净额",
                "经营活动现金流量净额",
                "NETCASH_OPERATE",
            )
        )
        capex = safe_float(
            pick_column(
                item,
                "购建固定资产、无形资产和其他长期资产支付的现金",
                "购建固定无形长期资产支付的现金",
            )
        )
        net_profit = safe_float(pick_column(item, "净利润", "NETPROFIT"))
        fcf = None
        if ocf is not None and capex is not None:
            fcf = round(ocf - abs(capex), 2)
        records.append(
            {
                "report_date": report_date,
                "operating_cash_flow": ocf,
                "capex": capex,
                "free_cash_flow": fcf,
                "net_profit": net_profit,
            }
        )
    records = sorted(records, key=lambda x: x.get("report_date") or "")
    if years > 0:
        records = records[-years:]
    return records


def summarize_dividend_quality(
    dividend_history: list[dict[str, Any]],
    cashflow_records: list[dict[str, Any]],
) -> dict[str, Any]:
    div_amounts = [item["cash_div_per_share"] for item in dividend_history if item.get("cash_div_per_share") is not None]
    dividend_cut_within_5y = False
    if len(div_amounts) >= 2:
        for idx in range(1, len(div_amounts)):
            prev, curr = div_amounts[idx - 1], div_amounts[idx]
            if prev > 0 and curr < prev * 0.8:
                dividend_cut_within_5y = True
                break
    fcf_values = [r.get("free_cash_flow") for r in cashflow_records if r.get("free_cash_flow") is not None]
    div_total_3y = sum(div_amounts[-3:]) if div_amounts else None
    fcf_total_3y = sum(fcf_values[-3:]) if fcf_values else None
    fcf_to_dividend_ratio_3y = None
    if div_total_3y and div_total_3y > 0 and fcf_total_3y is not None:
        fcf_to_dividend_ratio_3y = round(fcf_total_3y / div_total_3y * 100, 2)
    net_profits = [r.get("net_profit") for r in cashflow_records if r.get("net_profit") is not None]
    return {
        "dividend_cut_within_5y": dividend_cut_within_5y,
        "fcf_to_dividend_ratio_3y_pct": fcf_to_dividend_ratio_3y,
        "net_profit_volatility_pct": _volatility_pct([v for v in net_profits if v is not None]),
        "dividend_years_available": len(dividend_history),
    }


def fetch_cn_leverage_records(ak: Any, code: str, *, years: int = 5) -> list[dict[str, Any]]:
    try:
        bs_df = ak.stock_balance_sheet_by_report_em(symbol=code, indicator="按报告期")
    except Exception as exc:
        logger.warning("cn balance sheet failed %s: %s", code, exc)
        return []
    try:
        profit_df = ak.stock_profit_sheet_by_report_em(symbol=code, indicator="按报告期")
    except Exception as exc:
        logger.warning("cn profit sheet failed %s: %s", code, exc)
        profit_df = None
    if bs_df is None or bs_df.empty:
        return []
    profit_by_date: dict[str, dict[str, Any]] = {}
    if profit_df is not None and not profit_df.empty:
        for _, row in profit_df.iterrows():
            item = row.to_dict()
            report_date = str(pick_column(item, "报告期", "REPORT_DATE") or "")[:10]
            profit_by_date[report_date] = item
    records: list[dict[str, Any]] = []
    for _, row in bs_df.iterrows():
        item = row.to_dict()
        report_date = str(pick_column(item, "报告期", "REPORT_DATE") or "")[:10]
        cash = safe_float(pick_column(item, "货币资金", "MONETARYFUNDS"))
        short_debt = safe_float(pick_column(item, "短期借款", "SHORT_LOAN"))
        long_debt = safe_float(pick_column(item, "长期借款", "LONG_LOAN"))
        bonds = safe_float(pick_column(item, "应付债券", "BOND_PAYABLE"))
        interest_debt = safe_float(pick_column(item, "带息负债", "INTEREST_DEBT"))
        total_debt = interest_debt
        if total_debt is None:
            parts = [v for v in (short_debt, long_debt, bonds) if v is not None]
            total_debt = sum(parts) if parts else None
        net_debt = None
        if total_debt is not None and cash is not None:
            net_debt = round(total_debt - cash, 2)
        profit_item = profit_by_date.get(report_date, {})
        ebitda = safe_float(
            pick_column(profit_item, "EBITDA", "ebitda", "息税折旧摊销前利润")
        )
        if ebitda is None:
            operating_profit = safe_float(
                pick_column(profit_item, "营业利润", "OPERATE_PROFIT", "operating_profit")
            )
            depreciation = safe_float(pick_column(profit_item, "折旧", "摊销", "资产减值损失"))
            if operating_profit is not None:
                ebitda = round(operating_profit + (depreciation or 0), 2)
        net_debt_to_ebitda = None
        if net_debt is not None and ebitda is not None and ebitda > 0:
            net_debt_to_ebitda = round(net_debt / ebitda, 4)
        records.append(
            {
                "report_date": report_date,
                "cash": cash,
                "interest_bearing_debt": total_debt,
                "net_debt": net_debt,
                "ebitda": ebitda,
                "net_debt_to_ebitda": net_debt_to_ebitda,
            }
        )
    records = sorted(records, key=lambda x: x.get("report_date") or "")
    if years > 0:
        records = records[-years:]
    return records


def summarize_leverage(leverage_records: list[dict[str, Any]]) -> dict[str, Any]:
    latest = leverage_records[-1] if leverage_records else {}
    return {
        "leverage_records": leverage_records,
        "latest_net_debt": latest.get("net_debt"),
        "latest_ebitda": latest.get("ebitda"),
        "latest_net_debt_to_ebitda": latest.get("net_debt_to_ebitda"),
    }


def compute_dividend_ttm_yield(
    ak: Any,
    code: str,
    market_key: str,
    price: float | None,
) -> float | None:
    if not price or price <= 0:
        return None
    try:
        if market_key == "HK":
            div_df = ak.stock_hk_dividend_payout_em(symbol=code)
        else:
            div_df = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
    except Exception:
        return None
    if div_df is None or div_df.empty:
        return None
    cutoff = datetime.now() - timedelta(days=365)
    total = 0.0
    for _, row in div_df.iterrows():
        item = row.to_dict()
        date_text = str(pick_column(item, "除权除息日", "公告日期", "派息日") or "")[:10]
        try:
            div_date = datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            continue
        if div_date < cutoff:
            continue
        cash = safe_float(pick_column(item, "派息", "现金分红", "每股派息"))
        if cash is not None:
            total += cash
    if total <= 0:
        return None
    return round(total / price * 100, 2)


def fetch_hk_leverage_records(ak: Any, code: str, *, years: int = 5) -> list[dict[str, Any]]:
    try:
        df = ak.stock_financial_hk_analysis_indicator_em(symbol=code, indicator="年度")
    except Exception as exc:
        logger.warning("hk leverage failed %s: %s", code, exc)
        return []
    if df is None or df.empty:
        return []
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        item = row.to_dict()
        report_date = str(pick_column(item, "报告期", "REPORT_DATE", "日期") or "")[:10]
        if not report_date:
            continue
        cash = safe_float(pick_column(item, "货币资金", "现金及现金等价物", "MONETARYFUNDS"))
        total_debt = safe_float(
            pick_column(item, "带息负债", "总负债", "INTEREST_DEBT", "TOTAL_LIAB")
        )
        net_debt = safe_float(pick_column(item, "净负债", "NET_DEBT"))
        if net_debt is None and total_debt is not None and cash is not None:
            net_debt = round(total_debt - cash, 2)
        ebitda = safe_float(pick_column(item, "EBITDA", "ebitda", "息税折旧摊销前利润"))
        if ebitda is None:
            operating_profit = safe_float(pick_column(item, "经营溢利", "营业利润", "OPERATING_PROFIT"))
            if operating_profit is not None:
                ebitda = operating_profit
        net_debt_to_ebitda = None
        if net_debt is not None and ebitda is not None and ebitda > 0:
            net_debt_to_ebitda = round(net_debt / ebitda, 4)
        records.append(
            {
                "report_date": report_date,
                "cash": cash,
                "interest_bearing_debt": total_debt,
                "net_debt": net_debt,
                "ebitda": ebitda,
                "net_debt_to_ebitda": net_debt_to_ebitda,
            }
        )
    cutoff_year = datetime.now().year - years + 1
    return [record for record in records if _year_from_date(record.get("report_date")) >= cutoff_year]


def enrich_fundamentals_payload(
    ak: Any,
    *,
    code: str,
    market_key: str,
    years: int,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if market_key == "HK":
        dividend_history = fetch_hk_dividend_history(ak, code, years=years)
        cashflow_records: list[dict[str, Any]] = []
        leverage_summary = summarize_leverage(fetch_hk_leverage_records(ak, code, years=years))
    else:
        dividend_history = fetch_cn_dividend_history(ak, code, years=years)
        cashflow_records = fetch_cn_cashflow_records(ak, code, years=years)
        leverage_summary = summarize_leverage(fetch_cn_leverage_records(ak, code, years=years))
        for record in records:
            report_date = record.get("report_date")
            if not report_date:
                continue
            match = next((r for r in cashflow_records if r.get("report_date") == report_date), None)
            if match:
                record["operating_cash_flow"] = match.get("operating_cash_flow")
                record["free_cash_flow"] = match.get("free_cash_flow")
                record["net_profit"] = match.get("net_profit")
    for record in records:
        report_date = record.get("report_date")
        if not report_date:
            continue
        lev = next(
            (r for r in leverage_summary.get("leverage_records", []) if r.get("report_date") == report_date),
            None,
        )
        if lev:
            record["net_debt"] = lev.get("net_debt")
            record["ebitda"] = lev.get("ebitda")
            record["net_debt_to_ebitda"] = lev.get("net_debt_to_ebitda")
    quality = summarize_dividend_quality(dividend_history, cashflow_records)
    payload = {
        "dividend_history": dividend_history,
        "cashflow_records": cashflow_records,
        **quality,
    }
    payload.update(
        {
            k: v
            for k, v in leverage_summary.items()
            if k != "leverage_records" or v
        }
    )
    if leverage_summary.get("leverage_records"):
        payload["leverage_records"] = leverage_summary["leverage_records"]
    return payload
