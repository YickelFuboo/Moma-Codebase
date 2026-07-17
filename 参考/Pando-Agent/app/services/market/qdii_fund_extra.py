import re
from typing import Any

from .utils import pick_column, retry_call, safe_float

_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


def _extract_pct(text: Any) -> float | None:
    if text is None:
        return None
    match = _PERCENT_RE.search(str(text))
    if not match:
        return None
    return safe_float(match.group(1))


def _find_column(columns: Any, *keywords: str) -> Any | None:
    for col in columns:
        text = str(col)
        if any(keyword in text for keyword in keywords):
            return col
    return None


def normalize_subscription_status(text: Any) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {"raw": None, "status": None, "subscription_open": None}
    lowered = raw.lower()
    if "暂停" in raw and "申购" in raw:
        return {"raw": raw, "status": "suspended", "subscription_open": False}
    if "开放" in raw or "正常" in raw or "open" in lowered:
        return {"raw": raw, "status": "open", "subscription_open": True}
    return {"raw": raw, "status": raw, "subscription_open": None}


def build_qdii_subscription_action(
    *,
    subscription_open: bool | None,
    premium_rate: float | None,
) -> dict[str, Any]:
    if subscription_open is True:
        return {"action": "subscribe", "note": "subscription open"}
    if subscription_open is False:
        premium = abs(premium_rate or 0)
        if premium < 2:
            return {
                "action": "on_exchange",
                "note": "subscription suspended; premium below 2%, on-exchange only",
            }
        return {
            "action": "abandon",
            "note": "subscription suspended and premium above 2%",
        }
    return {"action": "unknown", "note": "subscription status unavailable"}


def lookup_purchase_row(purchase_df: Any, symbol: str) -> dict[str, Any] | None:
    if purchase_df is None or getattr(purchase_df, "empty", True):
        return None
    code_col = _find_column(purchase_df.columns, "代码")
    if code_col is None:
        return None
    match = purchase_df[purchase_df[code_col].astype(str).str.strip() == str(symbol).strip()]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def parse_purchase_row(row: dict[str, Any]) -> dict[str, Any]:
    subscribe_col = _find_column(row.keys(), "申购")
    redeem_col = _find_column(row.keys(), "赎回")
    nav_col = _find_column(row.keys(), "净值", "最新")
    nav_date_col = _find_column(row.keys(), "时间", "日期")
    subscribe = normalize_subscription_status(row.get(subscribe_col) if subscribe_col else None)
    redeem = normalize_subscription_status(row.get(redeem_col) if redeem_col else None)
    return {
        "subscription_status": subscribe.get("status"),
        "subscription_status_raw": subscribe.get("raw"),
        "subscription_open": subscribe.get("subscription_open"),
        "redemption_status": redeem.get("status"),
        "redemption_status_raw": redeem.get("raw"),
        "latest_nav": safe_float(row.get(nav_col)) if nav_col else None,
        "latest_nav_date": str(row.get(nav_date_col))[:10] if nav_date_col and row.get(nav_date_col) else None,
        "source_purchase": "akshare/fund_purchase_em",
    }


def parse_overview_row(row: dict[str, Any]) -> dict[str, Any]:
    scale_col = _find_column(row.keys(), "资产规模", "规模")
    fee_col = _find_column(row.keys(), "管理费率", "管理费")
    custody_col = _find_column(row.keys(), "托管费率", "托管费")
    benchmark_col = _find_column(row.keys(), "业绩比较基准", "基准")
    return {
        "fund_scale_text": str(row.get(scale_col) or "").strip() if scale_col else None,
        "management_fee_pct": _extract_pct(row.get(fee_col)) if fee_col else None,
        "custody_fee_pct": _extract_pct(row.get(custody_col)) if custody_col else None,
        "benchmark": str(row.get(benchmark_col) or "").strip() if benchmark_col else None,
        "source_overview": "akshare/fund_overview_em",
    }


def parse_achievement_tracking(achievement_df: Any) -> dict[str, Any]:
    if achievement_df is None or achievement_df.empty:
        return {}
    period_col = achievement_df.columns[1]
    fund_col = achievement_df.columns[2]
    benchmark_col = achievement_df.columns[3]
    rank_col = achievement_df.columns[4] if len(achievement_df.columns) > 4 else None
    latest = None
    latest_year = -1
    for _, row in achievement_df.iterrows():
        period = str(row.get(period_col) or "").strip()
        if period.isdigit() and len(period) == 4:
            year = int(period)
            if year >= latest_year:
                latest_year = year
                latest = row
    if latest is None:
        latest = achievement_df.iloc[0]
    fund_return = safe_float(latest.get(fund_col))
    benchmark_return = safe_float(latest.get(benchmark_col))
    tracking_gap_pct = None
    if fund_return is not None and benchmark_return is not None:
        tracking_gap_pct = round(fund_return - benchmark_return, 4)
    rank_text = str(latest.get(rank_col)).strip() if rank_col is not None and latest.get(rank_col) is not None else None
    return {
        "return_period": str(latest.get(period_col) or "").strip(),
        "fund_return_pct": fund_return,
        "benchmark_return_pct": benchmark_return,
        "annual_benchmark_return_gap_pct": tracking_gap_pct,
        "peer_rank": rank_text,
        "is_daily_tracking_error": False,
        "note": "Annual fund vs benchmark return gap; not daily tracking error",
        "source_achievement": "akshare/fund_individual_achievement_xq",
    }


def fetch_qdii_fund_meta(
    ak: Any,
    symbol: str,
    *,
    purchase_df: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"symbol": symbol}
    purchase_row = lookup_purchase_row(purchase_df, symbol)
    if purchase_row:
        payload.update(parse_purchase_row(purchase_row))
    try:
        overview_df = retry_call(lambda: ak.fund_overview_em(symbol=symbol))
        if overview_df is not None and not overview_df.empty:
            payload.update(parse_overview_row(overview_df.iloc[0].to_dict()))
    except Exception:
        pass
    if payload.get("management_fee_pct") is None:
        try:
            fee_df = retry_call(lambda: ak.fund_fee_em(symbol=symbol, indicator="运作费用"))
            if fee_df is not None and not fee_df.empty:
                row = fee_df.iloc[0]
                for value in row.tolist():
                    text = str(value)
                    if "管理" in text:
                        payload["management_fee_pct"] = _extract_pct(text)
                    elif "托管" in text:
                        payload["custody_fee_pct"] = _extract_pct(text)
                payload.setdefault("source_fee", "akshare/fund_fee_em")
        except Exception:
            pass
    try:
        achievement_df = retry_call(lambda: ak.fund_individual_achievement_xq(symbol=symbol))
        payload.update(parse_achievement_tracking(achievement_df))
    except Exception:
        pass
    return payload
