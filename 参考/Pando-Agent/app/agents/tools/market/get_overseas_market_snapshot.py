from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_overseas_market_snapshot", toolset="market")
class GetOverseasMarketSnapshotTool(BaseTool):
    """海外配置一站式快照：全球指数估值、跨市场指标、QDII ETF 与建仓前技术面。"""

    @property
    def name(self) -> str:
        return "get_overseas_market_snapshot"

    @property
    def description(self) -> str:
        return (
            "Overseas allocation snapshot: global index PE percentiles, cross-market "
            "indicators, path-one/two flags, QDII premium/liquidity/subscription/fee/tracking, pre-entry technicals."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "QDII ETF codes; defaults to overseas skill universe",
                },
                "window_years": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 5,
                    "maximum": 10,
                },
                "include_technicals": {"type": "boolean", "default": True},
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
        symbols: list[str] | None = None,
        window_years: int = 10,
        include_technicals: bool = True,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_overseas_market_snapshot(
                symbols=symbols,
                window_years=window_years,
                include_technicals=include_technicals,
            )
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_overseas_market_snapshot")
