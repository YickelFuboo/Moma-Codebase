import json
from pathlib import Path
from typing import Any,Dict,List,Optional
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ...schemes import AgentContext, RuntimeContext
from .utils import todo_file


def _save(path:Path, todos:List[Dict[str,Any]])->None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")


@register_tool(name="todo_write", toolset="todo")
class TodoWriteTool(BaseTool):

    @property
    def name(self)->str:
        return "todo_write"

    @property
    def description(self)->str:
        return """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multistep tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos. Feel free to edit the todo list based on new information.
6. After completing a task - Mark it complete and add any new follow-up tasks
7. When you start working on a new task, mark the todo as in_progress. Ideally you should only have one todo as in_progress at a time. Complete existing tasks before starting new ones.

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully
   - cancelled: Task no longer needed

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Only have ONE task in_progress at any time
   - Complete current tasks before starting new ones
   - Cancel tasks that become irrelevant

3. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names

When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully."""

    @property
    def parameters(self)->Dict[str,Any]:
        return {
            "type":"object",
            "properties":{
                "todos":{
                    "type":"array",
                    "items":{
                        "type":"object",
                        "properties":{
                            "content":{
                                "type":"string",
                                "description":"Brief description of the task",
                            },
                            "status":{
                                "type":"string",
                                "enum":["pending","in_progress","completed","cancelled"],
                                "description":"Current status of the task",
                            },
                            "priority":{
                                "type":"string",
                                "enum":["high","medium","low"],
                                "description":"Priority level of the task",
                            },
                        },
                        "required":["content","status","priority"],
                    },
                    "description":"The updated todo list",
                },
            },
            "required":["todos"],
        }

    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallel(self) -> bool:
        return False

    async def execute(self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        todos:List[Dict[str,Any]],
    ) -> ToolResult:
        session_id = agent_ctx.session_id or ""
        if not session_id:
            return ToolErrorResult("todo_write: session_id is required")

        p = todo_file(session_id)
        _save(p, todos)
        remaining = len([t for t in todos if t.get("status")!="completed"])
        output = "\n".join([
            f"<path>{p.resolve()}</path>",
            f"<remaining>{remaining}</remaining>",
            "<todos>",
            json.dumps(todos, ensure_ascii=False, indent=2),
            "</todos>",
        ])
        return ToolSuccessResult(output)
