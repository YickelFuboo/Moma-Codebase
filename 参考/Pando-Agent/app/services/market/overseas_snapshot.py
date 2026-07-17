from typing import Any

from .technical import bars_to_frame, calc_ma, calc_rsi
from .utils import safe_float

DEFAULT_QDII_SYMBOLS = (
    "513500",
    "159612",
    "513100",
    "513030",
    "513000",
    "513520",
)

OVERSEAS_INDEX_CODES = (
    "000300",
    "000985",
    "HSI",
    "SPX",
    "NDX",
    "DAX",
    "N225",
)

INDEX_TO_QDII: dict[str, str] = {
    "SPX": "513500",
    "NDX": "513100",
    "DAX": "513030",
    "N225": "513520",
}


def compute_etf_entry_technicals(bars: list[dict[str, Any]]) -> dict[str, Any]:
    df = bars_to_frame(bars)
    if df.empty or len(df) < 60:
        return {"available": False, "reason": "insufficient_bars"}
    closes = df["close"]
    highs = df["high"] if "high" in df.columns else closes
    latest_close = safe_float(closes.iloc[-1])
    if latest_close is None:
        return {"available": False, "reason": "missing_close"}
    window = df.tail(min(260, len(df)))
    high_52w = safe_float(highs.tail(len(window)).max())
    low_52w = safe_float(window["low"].min() if "low" in window.columns else closes.min())
    rsi14 = calc_rsi(closes, 14)
    ma50 = calc_ma(closes, 50)
    price_52w_position_pct = None
    if high_52w is not None and low_52w is not None and high_52w > low_52w:
        price_52w_position_pct = round((latest_close - low_52w) / (high_52w - low_52w) * 100, 2)
    ma50_deviation_pct = None
    if ma50 not in (None, 0):
        ma50_deviation_pct = round((latest_close / ma50 - 1) * 100, 2)
    below_52w_high_85pct = high_52w is not None and latest_close < high_52w * 0.85
    rsi_below_65 = rsi14 is not None and rsi14 < 65
    ma50_deviation_ok = ma50_deviation_pct is not None and abs(ma50_deviation_pct) < 5.0
    pre_entry_filter_pass = bool(below_52w_high_85pct and rsi_below_65 and ma50_deviation_ok)
    return {
        "available": True,
        "latest_close": latest_close,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "price_52w_position_pct": price_52w_position_pct,
        "rsi14": rsi14,
        "ma50": ma50,
        "ma50_deviation_pct": ma50_deviation_pct,
        "below_52w_high_85pct": below_52w_high_85pct,
        "rsi_below_65": rsi_below_65,
        "ma50_deviation_ok": ma50_deviation_ok,
        "pre_entry_filter_pass": pre_entry_filter_pass,
        "pre_entry_action": "immediate" if pre_entry_filter_pass else "conditional",
    }


def build_overseas_relative_value(
    index_valuations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    csi300_pct = safe_float((index_valuations.get("000300") or {}).get("pe_percentile"))
    csi_all_pct = safe_float((index_valuations.get("000985") or {}).get("pe_percentile"))
    hsi_pct = safe_float((index_valuations.get("HSI") or {}).get("pe_percentile"))
    path_one_bubble_hedge = (
        csi_all_pct is not None
        and hsi_pct is not None
        and csi_all_pct > 95
        and hsi_pct > 95
    )
    path_two_candidates: list[dict[str, Any]] = []
    for code in ("SPX", "NDX", "DAX", "N225"):
        payload = index_valuations.get(code) or {}
        pe_pct = safe_float(payload.get("pe_percentile"))
        gap_pp = None
        eligible = False
        if pe_pct is not None and csi300_pct is not None:
            gap_pp = round(csi300_pct - pe_pct, 2)
            eligible = pe_pct < 30 and gap_pp >= 20
        path_two_candidates.append(
            {
                "index": code,
                "pe_percentile": pe_pct,
                "gap_vs_csi300_pp": gap_pp,
                "eligible": eligible,
                "recommended_qdii": INDEX_TO_QDII.get(code),
            }
        )
    return {
        "csi300_pe_percentile": csi300_pct,
        "csi_all_pe_percentile": csi_all_pct,
        "hsi_pe_percentile": hsi_pct,
        "path_one_bubble_hedge": path_one_bubble_hedge,
        "path_two_candidates": path_two_candidates,
    }
