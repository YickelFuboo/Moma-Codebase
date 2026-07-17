from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_sector_liquidity", toolset="market")
class GetSectorLiquidityTool(BaseTool):
    """获取行业成交额占全市场比例及历史分位。"""

    @property
    def name(self) -> str:
        return "get_sector_liquidity"

    @property
    def description(self) -> str:
        return (
            "Sector turnover share vs whole market (000985 proxy), percentile, "
            "and ban_sector_etf flag when high-percentile streak is met."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "Industry board name, e.g. 半导体"},
                "window_years": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
                "consecutive_days": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "high_percentile": {"type": "number", "default": 90.0, "minimum": 50, "maximum": 99},
            },
            "required": ["sector"],
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
        sector: str,
        window_years: int = 5,
        consecutive_days: int = 5,
        high_percentile: float = 90.0,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_sector_liquidity(
                sector,
                window_years=window_years,
                consecutive_days=consecutive_days,
                high_percentile=high_percentile,
            )
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_sector_liquidity")
