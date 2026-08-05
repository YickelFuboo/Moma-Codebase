"""MCP 查询结果信封：与 CLI schemes 对齐。"""
from __future__ import annotations
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional
import click
from app.cli.common import run_async
from app.cli.schemes import ErrorCode, ResponseScheme


class McpEnvelope:
    """把异步查询结果包装成稳定 JSON 信封（不写 stdout、不 sys.exit）。"""

    @classmethod
    def success(cls, payload: Mapping[str, Any], *, profile: str = ResponseScheme.PROFILE_SEARCH) -> Dict[str, Any]:
        body = ResponseScheme.success(payload)
        if "total" not in body and isinstance(body.get("items"), list):
            body["total"] = len(body["items"])
        ResponseScheme.assert_envelope(body, profile=profile)
        return body

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        *,
        details: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = ResponseScheme.failure(code, message, details=details)
        ResponseScheme.assert_envelope(body, profile=ResponseScheme.PROFILE_SEARCH)
        return body

    @classmethod
    def from_exception(cls, exc: BaseException, *, timeout_ms: int = 0) -> Dict[str, Any]:
        if isinstance(exc, TimeoutError):
            return cls.failure(
                ErrorCode.TIMEOUT,
                str(exc),
                details={"timeout_ms": timeout_ms} if timeout_ms else None,
            )
        if isinstance(exc, click.ClickException):
            code = getattr(exc, "error_code", None) or ResponseScheme.classify_click_message(str(exc))
            details = getattr(exc, "details", None)
            return cls.failure(
                code,
                str(exc),
                details=details if isinstance(details, Mapping) else None,
            )
        error_code = getattr(exc, "error_code", None)
        if error_code == ErrorCode.INDEX_NOT_READY:
            details = getattr(exc, "details", None)
            return cls.failure(
                ErrorCode.INDEX_NOT_READY,
                str(exc),
                details=details if isinstance(details, Mapping) else None,
            )
        return cls.failure(ErrorCode.SYSTEM, str(exc))

    @classmethod
    def run(
        cls,
        coro_factory: Callable[[], Awaitable[Dict[str, Any]]],
        *,
        timeout_ms: int = 0,
        profile: str = ResponseScheme.PROFILE_SEARCH,
        postprocess: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        async def _job() -> Dict[str, Any]:
            return await ResponseScheme.run_with_timeout(coro_factory(), timeout_ms)

        try:
            out = run_async(_job)
            if postprocess is not None:
                out = postprocess(out)
            return cls.success(out, profile=profile)
        except Exception as exc:
            return cls.from_exception(exc, timeout_ms=timeout_ms)
