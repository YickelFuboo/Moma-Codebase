from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_market_volatility", toolset="market")
class GetMarketVolatilityTool(BaseTool):
    """获取市场波动率辅助指标（VIX、指数日内振幅等）。"""

    @property
    def name(self) -> str:
        return "get_market_volatility"

    @property
    def description(self) -> str:
        return (
            "Get volatility regime helpers: US VIX level/percentile, "
            "A-share index daily range and consecutive >3% days, CN 300 QVIX."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "default": "000300",
                    "description": "A-share benchmark for daily range stats, default CSI 300",
                },
                "days": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 120,
                    "default": 20,
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
        index: str = "000300",
        days: int = 20,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_market_volatility(index=index, days=days)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_market_volatility", index=index)
