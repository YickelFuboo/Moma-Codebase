from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_cash_market_snapshot", toolset="market")
class GetCashMarketSnapshotTool(BaseTool):
    """现金管理快照：GC001、DR007、货基7日年化排名。"""

    @property
    def name(self) -> str:
        return "get_cash_market_snapshot"

    @property
    def description(self) -> str:
        return (
            "Cash management snapshot: GC001, DR007 monthly avg, cn_1y, money/short-bond fund ranks, "
            "repo-vs-fund spread flags. ncd_1y and deposit_rate_benchmark return available:false "
            "when no official feed (use web_fetch)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 3,
                    "maximum": 30,
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
        top_n: int = 10,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_cash_market_snapshot(top_n=top_n)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_cash_market_snapshot")
