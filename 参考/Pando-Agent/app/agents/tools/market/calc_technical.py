from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="calc_technical", toolset="market")
class CalcTechnicalTool(BaseTool):
    """计算均线、量比、RSI、箱体与突破等技术指标。"""

    @property
    def name(self) -> str:
        return "calc_technical"

    @property
    def description(self) -> str:
        return (
            "Compute technical indicators (MA, volume ratio, RSI, box pattern, breakout) "
            "from historical bars without sending raw candles to the model."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol"},
                "freq": {
                    "type": "string",
                    "enum": ["1d", "1w", "1m"],
                    "default": "1d",
                },
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "e.g. ma60, ma120, volume_ratio_20d, rsi14, box_pattern, weekly_divergence",
                },
                "start": {"type": "string"},
                "end": {"type": "string"},
                "adjust": {
                    "type": "string",
                    "enum": ["qfq", "hfq", "none"],
                    "default": "qfq",
                },
                "market": {
                    "type": "string",
                    "enum": ["CN_A", "HK"],
                },
                "bar_limit": {
                    "type": "integer",
                    "minimum": 60,
                    "maximum": 500,
                    "default": 260,
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
        indicators: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        adjust: str = "qfq",
        market: str | None = None,
        bar_limit: int = 260,
    ) -> ToolResult:
        try:
            payload = await get_market_client().calc_technical(
                symbol,
                freq=freq,
                indicators=indicators,
                start=start,
                end=end,
                adjust=adjust,
                market=market,
                bar_limit=bar_limit,
            )
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="calc_technical", symbol=symbol)
