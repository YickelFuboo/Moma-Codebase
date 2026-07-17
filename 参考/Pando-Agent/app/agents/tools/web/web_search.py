from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ...schemes import AgentContext, RuntimeContext
from app.infrastructure.web_search.client import WebSearchClient


@register_tool(name="web_search", toolset="web")
class WebSearchTool(BaseTool):
    """Web 搜索工具，支持 Tavily / Brave / Serper / DuckDuckGo 及自动回退。"""

    def __init__(self, max_results: int = 5) -> None:
        self.max_results = max_results
        self._client = WebSearchClient()

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web and return titles, URLs, and snippets."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
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
        query: str,
        count: int | None = None,
    ) -> ToolResult:
        try:
            n = min(max(count or self.max_results, 1), 10)
        except Exception:
            n = self.max_results

        try:
            results, provider, attempted = await self._client.search(query, count=n)
        except Exception as e:
            return ToolErrorResult(f"Error calling web search: {e}")

        if not attempted:
            return ToolErrorResult(
                "No search provider configured. Set TAVILY_API_KEY, BRAVE_API_KEY, SERPER_API_KEY, or WEB_SEARCH_PRIMARY=duckduckgo in env."
            )

        if not results:
            return ToolSuccessResult(f"No results for: {query} (provider={provider})")

        lines: list[str] = [f"Results for: {query} (provider={provider})\n"]
        for i, item in enumerate(results[:n], 1):
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("content", "")
            lines.append(f"{i}. {title}\n   {url}")
            if desc:
                lines.append(f"   {desc}")

        return ToolSuccessResult("\n".join(lines))
