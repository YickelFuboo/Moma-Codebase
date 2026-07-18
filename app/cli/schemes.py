from __future__ import annotations
import asyncio
import json
import sys
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, TypeVar
import click

T = TypeVar("T")


class ExitCode:
    """mcb CLI 约定退出码。"""

    OK = 0
    USAGE = 1
    BUSINESS = 2
    TIMEOUT = 3
    SYSTEM = 4


class ErrorCode:
    """失败 JSON 中 error.code 的稳定枚举。"""

    BUSINESS = "business_error"
    REPO_NOT_FOUND = "repo_not_found"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    INVALID_PAYLOAD = "invalid_payload"
    SYSTEM = "system_error"


class ResponseScheme:
    """CLI JSON 输出信封与校验。"""

    PROFILE_RESOLVE = "resolve"
    PROFILE_SEARCH = "search"
    REQUIRED_ERROR_INNER = ("code", "message")

    @staticmethod
    def success(payload: Mapping[str, Any]) -> Dict[str, Any]:
        data = dict(payload)
        data["ok"] = True
        return data

    @staticmethod
    def failure(
        code: str,
        message: str,
        *,
        details: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        err: Dict[str, Any] = {
            "code": str(code or ErrorCode.BUSINESS),
            "message": str(message or ""),
        }
        if details:
            err["details"] = dict(details)
        return {"ok": False, "error": err}

    @classmethod
    def classify_click_message(cls, message: str) -> str:
        text = str(message or "")
        if "仓库未登记" in text or "未找到匹配的已登记仓库" in text:
            return ErrorCode.REPO_NOT_FOUND
        if "无权限" in text:
            return ErrorCode.PERMISSION_DENIED
        return ErrorCode.BUSINESS

    @classmethod
    def validate_search_success(cls, payload: Mapping[str, Any]) -> List[str]:
        """单能力 / 通用检索：ok + items + total。"""
        errors: List[str] = []
        if payload.get("ok") is not True:
            errors.append("ok 必须为 true")
        if "items" not in payload:
            errors.append("缺少字段: items")
        elif not isinstance(payload.get("items"), list):
            errors.append("items 必须为 list")
        if "total" not in payload:
            errors.append("缺少字段: total")
        elif not isinstance(payload.get("total"), int):
            errors.append("total 必须为 int")
        return errors

    @classmethod
    def validate_resolve_success(cls, payload: Mapping[str, Any]) -> List[str]:
        """resolve：在通用检索基础上再要求 query，且 item 有定位字段。"""
        errors = cls.validate_search_success(payload)
        if "query" not in payload:
            errors.append("缺少字段: query")
        items = payload.get("items")
        if isinstance(items, list):
            for i, it in enumerate(items):
                if not isinstance(it, Mapping):
                    errors.append(f"items[{i}] 必须为 object")
                    continue
                if not (
                    it.get("file_path")
                    or it.get("symbol_name")
                    or it.get("title")
                    or it.get("api_name")
                ):
                    errors.append(
                        f"items[{i}] 至少含 file_path / symbol_name / title / api_name 之一"
                    )
        return errors

    @classmethod
    def validate_failure(cls, payload: Mapping[str, Any]) -> List[str]:
        errors: List[str] = []
        if payload.get("ok") is not False:
            errors.append("ok 必须为 false")
        err = payload.get("error")
        if not isinstance(err, Mapping):
            errors.append("error 必须为 object")
            return errors
        for key in cls.REQUIRED_ERROR_INNER:
            if key not in err or err.get(key) in (None, ""):
                errors.append(f"error.{key} 必填")
        return errors

    @classmethod
    def assert_envelope(
        cls,
        payload: Mapping[str, Any],
        *,
        profile: str = PROFILE_SEARCH,
    ) -> None:
        if payload.get("ok") is True:
            if profile == cls.PROFILE_RESOLVE:
                problems = cls.validate_resolve_success(payload)
            else:
                problems = cls.validate_search_success(payload)
        elif payload.get("ok") is False:
            problems = cls.validate_failure(payload)
        else:
            problems = ["ok 必须为 true 或 false"]
        if problems:
            raise ValueError(f"CLI 输出校验失败({profile}): " + "; ".join(problems))

    @classmethod
    def echo_success(
        cls,
        payload: Mapping[str, Any],
        *,
        profile: str = PROFILE_SEARCH,
    ) -> None:
        body = cls.success(payload)
        if "total" not in body and isinstance(body.get("items"), list):
            body["total"] = len(body["items"])
        cls.assert_envelope(body, profile=profile)
        click.echo(json.dumps(body, ensure_ascii=False, indent=2, default=str))

    @classmethod
    def echo_failure_and_exit(
        cls,
        code: str,
        message: str,
        *,
        exit_code: int = ExitCode.BUSINESS,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        body = cls.failure(code, message, details=details)
        cls.assert_envelope(body, profile=cls.PROFILE_SEARCH)
        click.echo(json.dumps(body, ensure_ascii=False, indent=2, default=str))
        sys.exit(exit_code)

    @classmethod
    def echo_click_exception_and_exit(cls, exc: click.ClickException) -> None:
        code = cls.classify_click_message(str(exc))
        cls.echo_failure_and_exit(code, str(exc), exit_code=ExitCode.BUSINESS)

    @staticmethod
    async def run_with_timeout(awaitable: Awaitable[T], timeout_ms: int) -> T:
        """timeout_ms<=0 表示不限制；超时抛 TimeoutError。"""
        if timeout_ms and timeout_ms > 0:
            try:
                return await asyncio.wait_for(awaitable, timeout=timeout_ms / 1000.0)
            except asyncio.TimeoutError as exc:
                raise TimeoutError(f"操作超时（{timeout_ms} ms）") from exc
        return await awaitable

    @classmethod
    def run_and_echo(
        cls,
        coro_factory: Callable[[], Awaitable[Dict[str, Any]]],
        *,
        timeout_ms: int = 0,
        profile: str = PROFILE_SEARCH,
        with_content: Optional[bool] = None,
        attach_snippet: Optional[Callable[[Dict[str, Any], bool], Dict[str, Any]]] = None,
        run_async: Optional[Callable[..., Any]] = None,
    ) -> None:
        """执行异步检索并按 schemes 输出；统一处理超时与 ClickException。"""
        if run_async is None:
            from app.cli.common import run_async as _run_async

            run_async = _run_async

        async def _job() -> Dict[str, Any]:
            return await cls.run_with_timeout(coro_factory(), timeout_ms)

        try:
            out = run_async(_job)
            if with_content is not None and attach_snippet is not None:
                out = attach_snippet(out, with_content)
            cls.echo_success(out, profile=profile)
        except TimeoutError as exc:
            cls.echo_failure_and_exit(
                ErrorCode.TIMEOUT,
                str(exc),
                exit_code=ExitCode.TIMEOUT,
                details={"timeout_ms": timeout_ms},
            )
        except click.ClickException as exc:
            cls.echo_click_exception_and_exit(exc)
