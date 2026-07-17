from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="screen_etfs", toolset="market")
class ScreenEtfsTool(BaseTool):
    """按成交额、折溢价、涨跌幅等条件筛选 ETF。"""

    @property
    def name(self) -> str:
        return "screen_etfs"

    @property
    def description(self) -> str:
        return "Screen ETFs by amount, premium/discount, turnover, and name keywords."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": "amount_min, turnover_rate_min, premium_rate_max, name_keywords, exclude_leveraged",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["amount", "turnover_rate", "change_pct", "premium_rate"],
                    "default": "amount",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
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
        filters: dict[str, Any] | None = None,
        sort_by: str = "amount",
        limit: int = 50,
    ) -> ToolResult:
        try:
            payload = await get_market_client().screen_etfs(filters=filters, sort_by=sort_by, limit=limit)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="screen_etfs")
