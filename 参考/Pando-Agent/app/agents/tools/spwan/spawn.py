from typing import Any, TYPE_CHECKING
from ..base import BaseTool
from ..catalog import register_tool
from ..policy import DELEGATION_TOOL_NAME, SUBAGENT_TOOLSET
from ..schemes import ToolErrorResult, ToolResult, ToolSuccessResult
from ...schemes import AgentContext, RuntimeContext
if TYPE_CHECKING:
    from ...core.subagent import SubAgentManager


@register_tool(name=DELEGATION_TOOL_NAME, toolset=SUBAGENT_TOOLSET)
class SpawnTool(BaseTool):
    """Tool to spawn a subagent for background task execution."""
    
    @property
    def name(self) -> str:
        return DELEGATION_TOOL_NAME
    
    @property
    def description(self) -> str:
        return (
            "Spawn a subagent for a focused subtask and return a concise result. "
            "Use this when work is long-running, tool-intensive, or data-heavy, and detailed intermediate process should stay out of the main context. "
            "Typical examples include summarizing many files, scanning logs or search results for key findings, or running a multi-step investigation and reporting conclusions. "
            "Do not use spawn for tiny one-step actions or tasks that require frequent back-and-forth coordination with the main agent. "
            "The subagent works with its own configured tools and returns distilled findings rather than full intermediate output. "
            "Execution mode: mode='sync' (default) waits and returns subagent result in this call; mode='async' returns task id immediately and sends completion notification later. "
            "Write `task` as clear scope + expected output (goal, boundaries, and desired result format), not raw pasted data."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "A single, clear task for the subagent to complete (e.g. 'Summarize the key responsibilities "
                                   "and public APIs of files A, B, and C', or 'Scan recent logs and explain the most likely root cause "
                                   "of failures'). Avoid including raw file contents or very long text here; describe the goal and scope "
                                   "instead of pasting data.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["sync", "async"],
                    "description": "Optional. Execution mode. 'sync' waits and returns result in this call. 'async' returns task id immediately and notifies on completion. Default: 'sync'.",
                    "default": "sync",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display in logs/UI, e.g. a directory, feature, or topic name).",
                },
            },
            "required": ["task"],
        }
    
    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallel(self) -> bool:
        return False

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        task: str,
        *,
        mode: str = "sync",
        label: str | None = None,
    ) -> ToolResult:
        """Spawn a subagent to execute the given task."""
        subagent_manager = agent_ctx.subagent_manager
        if subagent_manager is None:
            return ToolErrorResult("spawn is not available: subagent_manager is not configured")
        text = await subagent_manager.start_task(
            task,
            run_ctx,
            mode=mode,
            label=label,
        )
        return ToolSuccessResult(text)
