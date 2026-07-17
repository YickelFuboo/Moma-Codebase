from typing import Any, Dict, Optional
from ..base import BaseTool
from ..schemes import ToolErrorResult, ToolResult, ToolSuccessResult
from ...schemes import AgentContext, RuntimeContext
from ...mcp.bridge import mcp_bridge_from_run_ctx


class MCPListPromptsTool(BaseTool):

    @property
    def name(self) -> str:
        return "mcp_list_prompts"

    @property
    def description(self) -> str:
        return (
            "List prompt templates exposed by connected MCP servers. "
            "Use mcp_get_prompt with a prompt name and optional arguments."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "Optional MCP server id from config. Omit to list all servers with prompts enabled.",
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
            text = await bridge.list_prompts(server_id, run_ctx=run_ctx)
            if text is None:
                if run_ctx.is_aborted():
                    return run_ctx.aborted_tool_result(self.name)
                return ToolErrorResult("mcp_list_prompts failed: no result")
            return ToolSuccessResult(text)
        except Exception as e:
            return ToolErrorResult(f"mcp_list_prompts failed: {e}")


class MCPGetPromptTool(BaseTool):

    @property
    def name(self) -> str:
        return "mcp_get_prompt"

    @property
    def description(self) -> str:
        return (
            "Fetch a filled prompt from an MCP server (messages with role/content). "
            "Use mcp_list_prompts to discover names and required arguments."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Prompt template name from mcp_list_prompts.",
                },
                "arguments": {
                    "type": "object",
                    "description": "Optional key-value arguments required by the prompt template.",
                    "additionalProperties": {"type": "string"},
                },
                "server_id": {
                    "type": "string",
                    "description": "Optional MCP server id when multiple servers expose prompts.",
                },
            },
            "required": ["name"],
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
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_id: Optional[str] = None,
    ) -> ToolResult:
        bridge = mcp_bridge_from_run_ctx(run_ctx)
        if bridge is None or not bridge.servers:
            return ToolErrorResult("No MCP servers connected")
        try:
            text = await bridge.get_prompt(name, arguments, server_id, run_ctx=run_ctx)
            if text is None:
                if run_ctx.is_aborted():
                    return run_ctx.aborted_tool_result(self.name)
                return ToolErrorResult("mcp_get_prompt failed: no result")
            if text.startswith("Failed") or text == "name is required":
                return ToolErrorResult(text)
            return ToolSuccessResult(text)
        except Exception as e:
            return ToolErrorResult(f"mcp_get_prompt failed: {e}")
