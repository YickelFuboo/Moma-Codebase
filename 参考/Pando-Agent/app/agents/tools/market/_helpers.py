import json
from typing import Any
from app.services.market import get_market_service, market_json_result
from ..schemes import ToolErrorResult, ToolSuccessResult, ToolResult

_service = None


def get_market_client():
    global _service
    if _service is None:
        _service = get_market_service()
    return _service


def market_success(payload: dict[str, Any]) -> ToolResult:
    return ToolSuccessResult(market_json_result(payload))


def market_error(message: str, **extra: Any) -> ToolResult:
    payload = {"error": message}
    payload.update(extra)
    return ToolErrorResult(json.dumps(payload, ensure_ascii=False))
