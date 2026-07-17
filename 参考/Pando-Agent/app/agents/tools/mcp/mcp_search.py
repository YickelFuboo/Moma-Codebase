from typing import Any, Dict, List, Optional
from ..base import BaseTool
from ..schemes import ToolErrorResult, ToolResult, ToolSuccessResult
from ...schemes import AgentContext, RuntimeContext
from ...mcp.bridge import mcp_bridge_from_run_ctx


class MCPSearchToolsTool(BaseTool):

    @property
    def name(self) -> str:
        return "mcp_search_tools"

    @property
    def description(self) -> str:
        return (
            "Search MCP tools when servers use lazy loading (lazy=true). "
            "Lists pending tools by optional query; pass activate with registry names "
            "(e.g. mcp_playwright_browser_navigate) to load full schemas for later turns."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional keyword to filter tool names/descriptions.",
                },
                "server_id": {
                    "type": "string",
                    "description": "Optional MCP server id to scope the search.",
                },
                "activate": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Registry tool names to load (full schema) for subsequent calls.",
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
        query: Optional[str] = None,
        server_id: Optional[str] = None,
        activate: Optional[List[str]] = None,
    ) -> ToolResult:
        bridge = mcp_bridge_from_run_ctx(run_ctx)
        if bridge is None or not bridge.servers:
            return ToolErrorResult("No MCP servers connected")
        try:
            text = await bridge.search_tools(query, server_id, activate, run_ctx=run_ctx)
            if text is None:
                if run_ctx.is_aborted():
                    return run_ctx.aborted_tool_result(self.name)
                return ToolErrorResult("mcp_search_tools failed: no result")
            return ToolSuccessResult(text)
        except Exception as e:
            return ToolErrorResult(f"mcp_search_tools failed: {e}")
