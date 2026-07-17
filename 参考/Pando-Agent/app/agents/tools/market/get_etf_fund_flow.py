from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_etf_fund_flow", toolset="market")
class GetEtfFundFlowTool(BaseTool):
    """获取宽基 ETF 及全市场主力资金流向。"""

    @property
    def name(self) -> str:
        return "get_etf_fund_flow"

    @property
    def description(self) -> str:
        return (
            "Get ETF and market main fund flow: broad ETF basket net inflow over "
            "recent weeks, ETF spot inflow today, and market daily series."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "weeks": {"type": "integer", "default": 4, "minimum": 1, "maximum": 12},
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
        weeks: int = 4,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_etf_fund_flow(weeks=weeks)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_etf_fund_flow")
