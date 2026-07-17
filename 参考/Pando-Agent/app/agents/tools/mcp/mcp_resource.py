from typing import Any, Dict, Optional
from ..base import BaseTool
from ..schemes import ToolErrorResult, ToolResult, ToolSuccessResult
from ...schemes import AgentContext, RuntimeContext
from ...mcp.bridge import mcp_bridge_from_run_ctx


class MCPListResourcesTool(BaseTool):

    @property
    def name(self) -> str:
        return "mcp_list_resources"

    @property
    def description(self) -> str:
        return (
            "List read-only resources exposed by connected MCP servers (docs, schemas, URIs). "
            "Use mcp_read_resource with a uri from this list."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "Optional MCP server id from config (e.g. playwright). Omit to list all servers.",
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
        server_id: Optional[str] = None,
    ) -> ToolResult:
        bridge = mcp_bridge_from_run_ctx(run_ctx)
        if bridge is None or not bridge.servers:
            return ToolErrorResult("No MCP servers connected")
        try:
            text = await bridge.list_resources(server_id, run_ctx=run_ctx)
            if text is None:
                if run_ctx.is_aborted():
                    return run_ctx.aborted_tool_result(self.name)
                return ToolErrorResult("mcp_list_resources failed: no result")
            return ToolSuccessResult(text)
        except Exception as e:
            return ToolErrorResult(f"mcp_list_resources failed: {e}")


class MCPReadResourceTool(BaseTool):

    @property
    def name(self) -> str:
        return "mcp_read_resource"

    @property
    def description(self) -> str:
        return "Read a resource URI from an MCP server. Use mcp_list_resources to discover URIs."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "uri": {
                    "type": "string",
                    "description": "Resource URI returned by mcp_list_resources.",
                },
                "server_id": {
                    "type": "string",
                    "description": "Optional MCP server id when multiple servers expose the same URI pattern.",
                },
            },
            "required": ["uri"],
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
        uri: str,
        server_id: Optional[str] = None,
    ) -> ToolResult:
        bridge = mcp_bridge_from_run_ctx(run_ctx)
        if bridge is None or not bridge.servers:
            return ToolErrorResult("No MCP servers connected")
        try:
            text = await bridge.read_resource(uri, server_id, run_ctx=run_ctx)
            if text is None:
                if run_ctx.is_aborted():
                    return run_ctx.aborted_tool_result(self.name)
                return ToolErrorResult("mcp_read_resource failed: no result")
            if text.startswith("Failed") or text == "uri is required":
                return ToolErrorResult(text)
            return ToolSuccessResult(text)
        except Exception as e:
            return ToolErrorResult(f"mcp_read_resource failed: {e}")
