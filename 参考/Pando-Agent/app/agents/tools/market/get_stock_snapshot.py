from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_stock_snapshot", toolset="market")
class GetStockSnapshotTool(BaseTool):
    """获取单只股票行情与关键基本面快照（PE/PB/ROE/毛利率等）。"""

    @property
    def name(self) -> str:
        return "get_stock_snapshot"

    @property
    def description(self) -> str:
        return "Get a single stock quote snapshot plus key fundamentals for validation."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol, e.g. 600519 or 00700"},
                "market": {
                    "type": "string",
                    "enum": ["CN_A", "HK"],
                    "description": "Optional market hint",
                },
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
        market: str | None = None,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_stock_snapshot(symbol, market=market)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_stock_snapshot", symbol=symbol)
