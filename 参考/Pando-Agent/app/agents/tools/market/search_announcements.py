from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="search_announcements", toolset="market")
class SearchAnnouncementsTool(BaseTool):
    """检索个股近期公告/新闻线索。"""

    @property
    def name(self) -> str:
        return "search_announcements"

    @property
    def description(self) -> str:
        return "Search recent announcements/news items for a stock as audit clues."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
                "market": {"type": "string", "enum": ["CN_A", "HK"]},
            },
            "required": ["symbol"],
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
        symbol: str,
        limit: int = 10,
        market: str | None = None,
    ) -> ToolResult:
        try:
            payload = await get_market_client().search_announcements(
                symbol, limit=limit, market=market
            )
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="search_announcements", symbol=symbol)
