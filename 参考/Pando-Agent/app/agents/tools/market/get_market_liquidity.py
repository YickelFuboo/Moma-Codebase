from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_market_liquidity", toolset="market")
class GetMarketLiquidityTool(BaseTool):
    """获取全市场/宽基成交额与历史分位（流动性枯竭辅助）。"""

    @property
    def name(self) -> str:
        return "get_market_liquidity"

    @property
    def description(self) -> str:
        return (
            "Get benchmark index turnover and historical percentile for liquidity regime checks "
            "(e.g. CSI All-Share 000985)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "default": "000985",
                    "description": "Benchmark index code, default CSI All-Share",
                },
                "window_years": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 1,
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
        index: str = "000985",
        window_years: int = 1,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_market_liquidity(
                window_years=window_years, index=index
            )
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_market_liquidity", index=index)
