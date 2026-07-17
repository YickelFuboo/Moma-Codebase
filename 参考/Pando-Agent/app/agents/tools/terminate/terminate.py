from typing import Dict
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult
from ...schemes import AgentContext, RuntimeContext
from ...sessions.message import Message


@register_tool(name="terminate", toolset="terminate")
class Terminate(BaseTool):
    """终止工具"""
    @property
    def name(self) -> str:
        return "terminate"
        
    @property
    def description(self) -> str:
        return """When you consider the task complete, or need to terminate the current task, you should use this tool."""
    
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",   
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "The summary of the task completion. It should be a brief description of the task completion process, the results or conclusions of the task.",
                }
            },
            "required": ["summary"]
        }      
    
    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallel(self) -> bool:
        return False

    async def execute(self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        summary: str,
    ) -> ToolResult:
        """Finish the current execution"""
        summary_text = (summary or "").strip()
        if summary_text and run_ctx.notify_user_callback is not None:
            await run_ctx.notify_user_callback(Message.assistant_message(summary_text))
        
        return ToolSuccessResult(f"The task has been completed with summary: {summary_text}")