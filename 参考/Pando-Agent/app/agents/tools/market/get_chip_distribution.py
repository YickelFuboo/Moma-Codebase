from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_chip_distribution", toolset="market")
class GetChipDistributionTool(BaseTool):
    """获取 A 股筹码分布（获利比例、平均成本、集中度）。"""

    @property
    def name(self) -> str:
        return "get_chip_distribution"

    @property
    def description(self) -> str:
        return "Get A-share chip distribution: profit ratio, average cost, concentration bands."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "market": {"type": "string", "enum": ["CN_A", "HK"], "default": "CN_A"},
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
        market: str | None = "CN_A",
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_chip_distribution(symbol, market=market)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_chip_distribution", symbol=symbol)
