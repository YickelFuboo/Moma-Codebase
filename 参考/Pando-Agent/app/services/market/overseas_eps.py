from typing import Any

from .data_integrity import unavailable_payload
from .schemes import global_index_em_name

OVERSEAS_EPS_INDEX_CODES = ("SPX", "NDX", "DAX", "N225")


def build_eps_growth_outlook(ak: Any, indices: tuple[str, ...] = OVERSEAS_EPS_INDEX_CODES) -> dict[str, Any]:
    outlook: dict[str, Any] = {}
    for code in indices:
        outlook[code] = unavailable_payload(
            reason="no_official_eps_growth_series",
            web_hint="web_fetch broker 12M EPS consensus or issuer filings",
            extra={"index": code, "index_name": global_index_em_name(code)},
        )
    return {
        "outlook_by_index": outlook,
        "note": "EPS growth is not provided by market service; use web_fetch for consensus data",
    }
