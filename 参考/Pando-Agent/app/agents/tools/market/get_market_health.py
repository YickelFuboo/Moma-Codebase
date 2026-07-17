from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_market_health", toolset="market")
class GetMarketHealthTool(BaseTool):
    """探测 market 数据服务可用性（生产运维）。"""

    @property
    def name(self) -> str:
        return "get_market_health"

    @property
    def description(self) -> str:
        return (
            "Probe market data service health: provider chain, macro rate and "
            "index valuation smoke checks. Use before batch analysis or in ops."
        )

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
            payload = await get_market_client().check_health()
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_market_health")
