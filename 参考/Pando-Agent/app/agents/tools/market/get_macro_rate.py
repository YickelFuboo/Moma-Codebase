from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult
from ...schemes import AgentContext, RuntimeContext
from ._helpers import get_market_client, market_error, market_success


@register_tool(name="get_macro_rate", toolset="market")
class GetMacroRateTool(BaseTool):
    """获取宏观利率（默认中国10年期国债收益率）。"""

    @property
    def name(self) -> str:
        return "get_macro_rate"

    @property
    def description(self) -> str:
        return (
            "Get macro interest rates from official/provider series only. "
            "Supported: cn_10y/cn_1y, dr007 (chinamoney repo), shibor_1w/1m, usdcny, tsf_yoy, "
            "gc001, lpr_1y/lpr_5y, us_10y. mlf/ncd_1y fail if no official feed (use web_fetch)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "enum": [
                        "cn_10y",
                        "cn_1y",
                        "dr007",
                        "shibor_1w",
                        "shibor_1m",
                        "usdcny",
                        "tsf_yoy",
                        "gc001",
                        "mlf",
                        "lpr_1y",
                        "lpr_5y",
                        "us_10y",
                        "ncd_1y",
                    ],
                    "default": "cn_10y",
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
        indicator: str = "cn_10y",
    ) -> ToolResult:
        try:
            payload = await get_market_client().get_macro_rate(indicator)
            return market_success(payload)
        except Exception as exc:
            return market_error(str(exc), tool="get_macro_rate")
