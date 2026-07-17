from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_bars", toolset="market")
class GetBarsTool(BaseTool):
    """获取指定个股历史 K 线：日线/周线/月线/分钟线。"""

    @property
    def name(self) -> str:
        return "get_bars"

    @property
    def description(self) -> str:
        return "Fetch historical OHLCV bars for a stock (daily/weekly/monthly/intraday)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol"},
                "freq": {
                    "type": "string",
                    "enum": ["1d", "1w", "1m", "1m_intraday", "5m_intraday"],
                    "default": "1d",
                },
                "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                "adjust": {
                    "type": "string",
                    "enum": ["qfq", "hfq", "none"],
                    "default": "qfq",
                },
                "market": {
                    "type": "string",
                    "enum": ["CN_A", "HK"],
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "description": "Return at most N most-recent bars",
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
        freq: str = "1d",
        start: str | None = None,
        end: str | None = None,
        adjust: str = "qfq",
        market: str | None = None,
        limit: int | None = None,
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_bars(
                symbol,
                freq=freq,
                start=start,
                end=end,
                adjust=adjust,
                market=market,
                limit=limit,
            )
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_bars", symbol=symbol)
