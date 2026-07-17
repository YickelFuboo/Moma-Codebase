import json
from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ...schemes import AgentContext, RuntimeContext
from app.infrastructure.web_fetch import WebFetcher, validate_fetch_url


@register_tool(name="web_fetch", toolset="web")
class WebFetchTool(BaseTool):
    """抓取 URL 并抽取可读内容，支持 static / Jina Reader / Tavily / Firecrawl 及自动回退。"""

    def __init__(self, max_chars: int = 50000) -> None:
        self.max_chars = max_chars
        self._fetcher = WebFetcher()

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch a URL and extract readable content (HTML → markdown/text)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "extractMode": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "default": "markdown",
                    "description": "Extraction mode for HTML pages",
                },
                "maxChars": {
                    "type": "integer",
                    "minimum": 100,
                    "description": "Maximum characters in extracted content",
                },
            },
            "required": ["url"],
        }

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallel(self) -> bool:
        return True

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        url: str,
        extractMode: str = "markdown",
        maxChars: int | None = None,
    ) -> ToolResult:
        max_chars = maxChars or self.max_chars

        is_valid, error_msg = validate_fetch_url(url)
        if not is_valid:
            return ToolErrorResult(
                json.dumps(
                    {"error": f"URL validation failed: {error_msg}", "url": url},
                    ensure_ascii=False,
                )
            )

        result = await self._fetcher.fetch(
            url,
            extract_mode=extractMode,
            max_chars=max_chars,
        )

        if result.get("error") and not result.get("text"):
            return ToolErrorResult(
                json.dumps(
                    {
                        "error": result["error"],
                        "url": url,
                        "attempted": result.get("attempted"),
                    },
                    ensure_ascii=False,
                )
            )

        payload = {
            "url": result.get("url", url),
            "finalUrl": result.get("final_url", url),
            "status": result.get("status", 0),
            "extractor": result.get("extractor", "unknown"),
            "truncated": result.get("truncated", False),
            "length": result.get("length", len(result.get("text", ""))),
            "text": result.get("text", ""),
        }
        if result.get("attempted"):
            payload["attempted"] = result["attempted"]
        return ToolSuccessResult(json.dumps(payload, ensure_ascii=False))
