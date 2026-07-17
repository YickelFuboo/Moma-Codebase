from typing import Any


def unavailable_payload(
    *,
    reason: str,
    web_hint: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "available": False,
        "reason": reason,
    }
    if web_hint:
        payload["web_hint"] = web_hint
    if extra:
        payload.update(extra)
    return payload
