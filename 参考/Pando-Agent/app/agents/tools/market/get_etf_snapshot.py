from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_etf_snapshot", toolset="market")
class GetEtfSnapshotTool(BaseTool):
    """获取 ETF 行情快照（价格、成交额、折溢价等）。"""

    @property
    def name(self) -> str:
        return "get_etf_snapshot"

    @property
    def description(self) -> str:
        return "Get ETF quote snapshot including price, turnover and premium/discount."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "ETF code, e.g. 510300"},
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
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_etf_snapshot(symbol)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_etf_snapshot", symbol=symbol)
