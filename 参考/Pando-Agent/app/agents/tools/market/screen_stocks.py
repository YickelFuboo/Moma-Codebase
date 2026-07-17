from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="screen_stocks", toolset="market")
class ScreenStocksTool(BaseTool):
    """按估值、流动性、涨跌幅等组合条件筛选 A 股/港股；复杂财务条件可用 wencai_query。"""

    @property
    def name(self) -> str:
        return "screen_stocks"

    @property
    def description(self) -> str:
        return (
            "Screen A-share or HK stocks by structured filters (PE/PB/market cap/turnover/etc) "
            "or by a Chinese natural-language wencai_query for multi-year financial conditions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "enum": ["CN_A", "HK"],
                    "default": "CN_A",
                    "description": "Market universe",
                },
                "filters": {
                    "type": "object",
                    "description": "Structured filters: pe_ttm_max, pb_max, amount_min, exclude_st, roe_min, gross_margin_min, consecutive_years, dividend_yield_min, ocf_to_net_income_min",
                },
                "wencai_query": {
                    "type": "string",
                    "description": "Optional pywencai Chinese query for complex financial screening",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["amount", "market_cap", "pe_ttm", "pb", "turnover_rate", "change_pct"],
                    "default": "amount",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 50,
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
        market: str = "CN_A",
        filters: dict[str, Any] | None = None,
        wencai_query: str | None = None,
        sort_by: str = "amount",
        limit: int = 50,
    ) -> ToolResult:
        try:
            payload = await get_market_client().screen_stocks(
                market=market,
                filters=filters,
                wencai_query=wencai_query,
                sort_by=sort_by,
                limit=limit,
            )
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="screen_stocks")
