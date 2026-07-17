from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_market_sentiment", toolset="market")
class GetMarketSentimentTool(BaseTool):
    """获取北向资金与两融等市场情绪指标。"""

    @property
    def name(self) -> str:
        return "get_market_sentiment"

    @property
    def description(self) -> str:
        return (
            "Get A-share market sentiment: northbound net flow, margin balances, "
            "and financing balance percentile for regime checks."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 60,
                    "description": "Number of recent trading days for northbound flow series",
                },
                "window_years": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Historical window for margin financing balance percentile",
                },
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
        days: int = 5,
        window_years: int = 5,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_market_sentiment(days=days, window_years=window_years)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_market_sentiment")
