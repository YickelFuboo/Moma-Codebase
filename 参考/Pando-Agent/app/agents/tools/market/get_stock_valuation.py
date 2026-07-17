from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_stock_valuation", toolset="market")
class GetStockValuationTool(BaseTool):
    """获取个股 PE-TTM 分位、PEG、股息率等估值指标。"""

    @property
    def name(self) -> str:
        return "get_stock_valuation"

    @property
    def description(self) -> str:
        return "Get stock valuation metrics: PE-TTM percentile, PEG, dividend yield."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "window_years": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
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
        window_years: int = 5,
        market: str | None = None,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_stock_valuation(symbol, window_years=window_years, market=market)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_stock_valuation", symbol=symbol)
