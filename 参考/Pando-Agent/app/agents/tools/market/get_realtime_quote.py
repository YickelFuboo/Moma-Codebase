from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_realtime_quote", toolset="market")
class GetRealtimeQuoteTool(BaseTool):
    """获取单只股票最新行情（通常为延迟行情）。"""

    @property
    def name(self) -> str:
        return "get_realtime_quote"

    @property
    def description(self) -> str:
        return "Get latest quote for a single A-share or HK stock."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol"},
                "market": {
                    "type": "string",
                    "enum": ["CN_A", "HK"],
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
            payload = await get_market_client().get_realtime_quote(symbol, market=market)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_realtime_quote", symbol=symbol)
