from typing import Any, Dict, List
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult
from ...schemes import AgentContext, RuntimeContext
from ...sessions.message import Message


@register_tool(name="ask_question", toolset="ask")
class AskQuestion(BaseTool):
    """Ask a question to the user."""
    @property
    def name(self) -> str:
        return "ask_question"
        
    @property
    def description(self) -> str:
        return """Use this tool when you need to ask the user questions during execution. This allows you to:
1. Gather user preferences or requirements
2. Clarify ambiguous instructions
3. Get decisions on implementation choices as you work
4. Offer choices to the user about what direction to take.

Usage notes:Do not use this tool unless necessary. You should strive to understand the user's intention and complete the user's task independently. Only use this tool to confirm with the user when it is absolutely necessary without user confirmation.
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "Questions to ask. For a single question, pass an array with one item.",
                    "items": {"type": "string"},
                }
            },
            "required": ["questions"]
        }    

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallel(self) -> bool:
        return False

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        questions: List[str]
    ) -> ToolResult:
        formatted = []
        for q in questions or []:
            text = (q or "").strip()
            formatted.append(f"{text}")
        
        questions_text = "\n".join(formatted)
        if questions_text and run_ctx.notify_user_callback is not None:
            await run_ctx.notify_user_callback(Message.assistant_message(questions_text))

        return ToolSuccessResult(f"The question has been asked to the user：{questions_text}")            