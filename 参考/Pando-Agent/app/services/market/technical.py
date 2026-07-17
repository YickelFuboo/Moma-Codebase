from typing import Any
import pandas as pd
from .utils import safe_float


def bars_to_frame(bars: list[dict[str, Any]]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame(bars)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
    for col in ("open", "high", "low", "close", "volume", "amount", "turnover"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def calc_ma(series: pd.Series, window: int) -> float | None:
    if series is None or len(series) < window:
        return None
    value = series.tail(window).mean()
    return None if pd.isna(value) else round(float(value), 4)


def calc_volume_ratio(volumes: pd.Series, window: int = 20) -> float | None:
    if volumes is None or len(volumes) < window + 1:
        return None
    avg = volumes.tail(window + 1).head(window).mean()
    latest = volumes.iloc[-1]
    if pd.isna(avg) or avg == 0 or pd.isna(latest):
        return None
    return round(float(latest / avg), 4)


def calc_rsi(closes: pd.Series, window: int = 14) -> float | None:
    if closes is None or len(closes) < window + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.tail(window).mean()
    avg_loss = loss.tail(window).mean()
    if pd.isna(avg_loss) or avg_loss == 0:
        return 100.0 if avg_gain and avg_gain > 0 else None
    rs = avg_gain / avg_loss
    return round(float(100 - (100 / (1 + rs))), 4)


def resample_bars(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty or "date" not in df.columns:
        return df
    indexed = df.set_index("date")
    agg = indexed.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        }
    )
    agg = agg.dropna(subset=["close"]).reset_index()
    agg["date"] = agg["date"].dt.strftime("%Y-%m-%d")
    return agg


def _find_box_bounds(window: pd.DataFrame) -> tuple[float | None, float | None]:
    highs = window["high"].astype(float)
    lows = window["low"].astype(float)
    best: tuple[float, float, int] | None = None
    for upper in sorted(set(round(v, 2) for v in highs.nlargest(8).tolist()), reverse=True):
        for lower in sorted(set(round(v, 2) for v in lows.nsmallest(8).tolist())):
            if lower <= 0 or upper <= lower:
                continue
            amp = (upper - lower) / lower
            if amp < 0.10 or amp > 0.25:
                continue
            touch_upper = int((highs >= upper * 0.995).sum())
            touch_lower = int((lows <= lower * 1.005).sum())
            if touch_upper >= 3 and touch_lower >= 3:
                score = touch_upper + touch_lower
                if best is None or score > best[2]:
                    best = (upper, lower, score)
    if best is None:
        return None, None
    return best[0], best[1]


def detect_box_pattern(df: pd.DataFrame, *, min_days: int = 20, max_days: int = 60) -> dict[str, Any]:
    if df.empty or len(df) < min_days:
        return {"detected": False, "reason": "insufficient_bars"}
    window = df.tail(max_days).copy()
    upper, lower = _find_box_bounds(window)
    if upper is None or lower is None:
        return {"detected": False, "reason": "no_valid_box"}
    amplitude = (upper - lower) / lower
    touch_upper = int((window["high"] >= upper * 0.995).sum())
    touch_lower = int((window["low"] <= lower * 1.005).sum())
    avg_volume = float(window["volume"].mean()) if "volume" in window.columns else None
    upper_peak = window.loc[window["high"] >= upper * 0.995, "volume"]
    upper_volume_peak = float(upper_peak.max()) if not upper_peak.empty else None
    detected = touch_upper >= 3 and touch_lower >= 3 and 0.10 <= amplitude <= 0.25 and len(window) >= 15
    return {
        "detected": detected,
        "box_upper": round(upper, 4),
        "box_lower": round(lower, 4),
        "box_height": round(upper - lower, 4),
        "amplitude_pct": round(amplitude * 100, 2),
        "touch_upper": touch_upper,
        "touch_lower": touch_lower,
        "window_days": len(window),
        "avg_volume": round(avg_volume, 2) if avg_volume is not None else None,
        "upper_volume_peak": round(upper_volume_peak, 2) if upper_volume_peak is not None else None,
    }


def calc_breakout_signal(df: pd.DataFrame, box: dict[str, Any]) -> dict[str, Any]:
    if df.empty or not box.get("detected"):
        return {"breakout": False, "reason": "no_box"}
    latest = df.iloc[-1]
    upper = box.get("box_upper")
    avg_volume = box.get("avg_volume")
    close = safe_float(latest.get("close"))
    volume = safe_float(latest.get("volume"))
    if upper is None or close is None:
        return {"breakout": False, "reason": "missing_values"}
    breakout_price = upper * 1.02
    volume_ok = volume is not None and avg_volume and volume >= avg_volume * 2
    price_ok = close >= breakout_price
    return {
        "breakout": bool(price_ok and volume_ok),
        "close": close,
        "breakout_price_threshold": round(breakout_price, 4),
        "volume_ratio_vs_box_avg": round(volume / avg_volume, 4) if volume and avg_volume else None,
        "price_breakout": price_ok,
        "volume_breakout": volume_ok,
    }


def detect_weekly_divergence(daily_bars: list[dict[str, Any]]) -> dict[str, Any]:
    df = bars_to_frame(daily_bars)
    if len(df) < 60:
        return {"detected": False, "reason": "insufficient_bars"}
    weekly = resample_bars(df, "W-FRI")
    if len(weekly) < 20:
        return {"detected": False, "reason": "insufficient_weeks"}
    closes = pd.to_numeric(weekly["close"], errors="coerce")
    recent = closes.tail(6)
    rsi_now = calc_rsi(closes, 14)
    low_idx = recent.idxmin()
    rsi_at_low = calc_rsi(closes.loc[:low_idx], 14)
    price_new_low = float(recent.iloc[-1]) <= float(recent.min()) * 1.01
    detected = bool(
        price_new_low
        and rsi_now is not None
        and rsi_at_low is not None
        and rsi_now > rsi_at_low
    )
    return {
        "detected": detected,
        "latest_close": safe_float(recent.iloc[-1]),
        "latest_rsi14": rsi_now,
        "rsi_at_recent_low": rsi_at_low,
    }


def compute_indicators(
    bars: list[dict[str, Any]],
    *,
    indicators: list[str],
    freq: str,
) -> dict[str, Any]:
    df = bars_to_frame(bars)
    if df.empty:
        return {"error": "no_bars"}
    raw_daily = df.copy()
    if freq == "1w":
        df = resample_bars(df, "W-FRI")
    elif freq == "1m":
        df = resample_bars(df, "ME")
    closes = df["close"]
    volumes = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)
    result: dict[str, Any] = {}
    requested = {item.strip().lower() for item in indicators if item}
    for name, window in (("ma5", 5), ("ma20", 20), ("ma60", 60), ("ma120", 120), ("ma250", 250)):
        if name in requested:
            result[name] = calc_ma(closes, window)
    if "volume_ratio_20d" in requested:
        result["volume_ratio_20d"] = calc_volume_ratio(volumes, 20)
    if "rsi14" in requested:
        result["rsi14"] = calc_rsi(closes, 14)
    if "box_pattern" in requested:
        box = detect_box_pattern(raw_daily if freq == "1d" else df)
        result["box_pattern"] = box
        result["breakout_signal"] = calc_breakout_signal(raw_daily if freq == "1d" else df, box)
    if "weekly_divergence" in requested:
        result["weekly_divergence"] = detect_weekly_divergence(bars)
    latest_close = safe_float(closes.iloc[-1]) if len(closes) else None
    ma60 = result.get("ma60")
    ma120 = result.get("ma120")
    if latest_close is not None and ma60 is not None:
        result["price_vs_ma60_pct"] = round((latest_close / ma60 - 1) * 100, 2)
        result["above_ma60"] = latest_close >= ma60
    if latest_close is not None and ma120 is not None:
        result["above_ma120"] = latest_close >= ma120
    if ma60 is not None and ma120 is not None:
        result["ma_bearish_alignment"] = ma60 < ma120
    if "volume_ratio_20d" in result and result["volume_ratio_20d"] is not None:
        result["shrink_volume"] = result["volume_ratio_20d"] < 0.7
    result["latest_close"] = latest_close
    result["bar_count"] = len(df)
    if "date" in df.columns and len(df):
        result["latest_date"] = str(df.iloc[-1]["date"])[:10]
    return result
