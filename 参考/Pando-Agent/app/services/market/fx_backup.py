import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_YAHOO_DXY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PandoHarness/1.0)"}


def fetch_dxy_yahoo_chart(*, range_: str = "3mo", interval: str = "1d") -> dict[str, Any] | None:
    try:
        import httpx
    except ImportError:
        return None
    try:
        with httpx.Client(timeout=20.0, trust_env=False) as client:
            resp = client.get(
                _YAHOO_DXY_URL,
                params={"range": range_, "interval": interval},
                headers=_YAHOO_HEADERS,
            )
            resp.raise_for_status()
            payload = resp.json()
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return None
        block = result[0]
        timestamps = block.get("timestamp") or []
        closes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        pairs = [(ts, close) for ts, close in zip(timestamps, closes) if close is not None]
        if not pairs:
            return None
        latest_ts, latest_val = pairs[-1]
        month_val = pairs[-22][1] if len(pairs) >= 22 else pairs[0][1]
        monthly_change = None
        if month_val not in (None, 0):
            monthly_change = round((latest_val - month_val) / month_val * 100, 4)
        return {
            "value": round(float(latest_val), 4),
            "date": datetime.fromtimestamp(latest_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "monthly_change_pct": monthly_change,
            "source": "yahoo/DX-Y.NYB",
        }
    except Exception as exc:
        logger.warning("yahoo dxy backup failed: %s", exc)
        return None
