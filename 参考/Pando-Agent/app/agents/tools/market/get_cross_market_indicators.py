from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_cross_market_indicators", toolset="market")
class GetCrossMarketIndicatorsTool(BaseTool):
    """获取 AH 溢价均值、USD/CNY 等跨市场指标。"""

    @property
    def name(self) -> str:
        return "get_cross_market_indicators"

    @property
    def description(self) -> str:
        return "Get cross-market indicators: AH premium, USD/CNY monthly change, US 10Y, DXY."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

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
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_cross_market_indicators()
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_cross_market_indicators")
