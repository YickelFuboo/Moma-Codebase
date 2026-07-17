from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_index_valuation", toolset="market")
class GetIndexValuationTool(BaseTool):
    """获取宽基指数 PE-TTM 及历史分位。"""

    @property
    def name(self) -> str:
        return "get_index_valuation"

    @property
    def description(self) -> str:
        return (
            "Get index PE-TTM and historical percentile for CSI/HSI and overseas benchmarks "
            "(SPX, NDX, DAX, N225)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "Index code or alias, e.g. 000985, 000300, HSI",
                },
                "window_years": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["index"],
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
        index: str,
        window_years: int = 5,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_index_valuation(index, window_years=window_years)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_index_valuation", index=index)
