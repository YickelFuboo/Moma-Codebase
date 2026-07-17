"""会话压缩：当 token 接近上下文上限时，用摘要替代长历史。"""
import json
import logging
import re
import time
from typing import List,Optional
from .message import Message,Role
from .session import Session
from app.config.settings import settings
from app.infrastructure.llms.chat_models.schemes import TokenUsage
from app.infrastructure.llms.utils import num_tokens_from_string


class SessionCompaction:
    COMPACTION_BUFFER = 20_000
    COMPACTION_SYSTEM = (
            """You are a session summarization agent.
Your task is to summarize the conversation history. The summary will be used as continuation context by another agent.
Do not continue the original task. Do not call tools. Summarize only. 

Your summary should focus on information that would be helpful for continuing the conversation, including what we did, what we're doing, which files we're working on, and what we're going to do next.

When constructing the summary, try to stick to this template:
---
## Goal

[What goal(s) is the user trying to accomplish?]

## Instructions

- [What important instructions did the user give you that are relevant]
- [If there is a plan or spec, include information about it so next agent can continue using it]

## Discoveries

[What notable things were learned during this conversation that would be useful for the next agent to know when continuing the work]

## Accomplished

[What work has been completed, what work is still in progress, and what work is left?]

## Relevant files / directories

[Construct a structured list of relevant files that have been read, edited, or created that pertain to the task at hand. If all the files in a directory are relevant, include the path to the directory.]
---
            """
        )

    @staticmethod
    def _looks_like_tool_output(text: str) -> bool:
        s = (text or "").lower()
        markers = ("<tool_call>", "<tool>", "<arg_key>", "<arg_value>", "</tool_call>")
        return any(m in s for m in markers)
    
    @staticmethod
    def is_overflow(
        *,
        usage: TokenUsage,
        llm: Optional[object] = None,
    ) -> bool:
        """判断当前 token 数是否接近上下文上限，需要触发压缩。

        Args:
            usage: 当前轮次的总 token 数（input + output 或 total）
            llm: 当前使用的 LLM 实例，用于读取模型配置（context_limit/max_tokens）

        Returns:
            True 表示溢出，应触发压缩
        """
        if not getattr(settings, "compaction_auto", True):
            return False
        
        llm_context_limit = None
        llm_max_output_tokens = None
        llm_max_input_tokens = None
        if llm is not None:
            limits = getattr(llm, "limits", None)
            llm_context_limit = getattr(limits, "context_limit", None)
            llm_max_output_tokens = getattr(limits, "max_output_tokens", None)
            llm_max_input_tokens = getattr(limits, "max_input_tokens", None)

        limit = llm_context_limit or getattr(settings, "compaction_context_limit", 128_000)
        res = int(getattr(settings, "compaction_reserved", 20_000) or 20_000)

        basis = usage.overflow_basis()

        if llm_max_input_tokens is not None and llm_max_input_tokens > 0:
            usable_in = llm_max_input_tokens - res
            if usable_in > 0 and basis >= usable_in:
                return True

        if limit <= 0:
            return False

        max_out = llm_max_output_tokens or 8192
        usable_ctx = limit - max_out - res  # 可用空间 = 上下文上限 - 下轮最大输出 token 数 - 为压缩预留的 token 缓冲
        if usable_ctx <= 0:
            return True
        return basis >= usable_ctx  # 当前输入 token 是否超过可用空间

    @staticmethod
    async def compact(
        *,
        llm: object,
        messages: List[Message],
        previous_summary: str = "",
    ) -> Optional[Message]:
        """生成会话摘要：将历史摘要（可选）与新增消息合并为新的摘要。"""
        if not messages:
            return None
        history = [m.to_context() for m in messages]
        prev = (previous_summary or "").strip()
        question = (
            "Please summarize the conversation history.\n"
        )
        if prev:
            question += (
                "\n\n[Previous Summary]\n"
                f"{prev}\n"
                "\nMerge the previous summary with the new conversation history and output one updated summary."
            )
        response, _ = await llm.chat(
            system_prompt=SessionCompaction.COMPACTION_SYSTEM,
            user_prompt="",
            user_question=question,
            history=history,
            temperature=0.1,
        )
        if not response or not response.success or not response.content:
            return None
        content = response.content.strip()
        # 清理可能混入的思考片段，避免污染 JSON 解析。
        content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()
        if not content or content.lower().startswith("llm error:"):
            return None
        if SessionCompaction._looks_like_tool_output(content):
            return None
        return Message(role=Role.ASSISTANT, content=content)


    @staticmethod
    def prune(messages: List[Message], start: int = 0) -> int:
        if not getattr(settings, "compaction_prune", True):
            return 0
        if not messages:
            return 0            
        if start < 0:
            start = 0
        if start >= len(messages):
            return 0

        protect = int(getattr(settings, "compaction_prune_protect", 40_000) or 40_000)
        minimum = int(getattr(settings, "compaction_prune_minimum", 20_000) or 20_000)
        protected_tools_raw = getattr(settings, "compaction_prune_protected_tools", "skill") or "skill"
        protected_tools = {t.strip() for t in protected_tools_raw.split(",") if t.strip()}

        candidates: List[Message] = []
        candidates_tokens = 0
        seen_tokens = 0

        scan = messages[start:]
        for msg in reversed(scan):
            if not msg.is_tool_result:
                continue
            if isinstance(msg.metadata, dict) and msg.metadata.get("pruned_at"):
                break
            if msg.name in protected_tools:
                continue
            t = num_tokens_from_string(msg.content or "")
            seen_tokens += t
            if seen_tokens <= protect:
                continue
            candidates.append(msg)
            candidates_tokens += t

        if candidates_tokens < minimum:
            return 0

        now_ms = int(time.time() * 1000)
        for msg in candidates:
            meta = msg.metadata if isinstance(msg.metadata, dict) else {}
            meta["pruned_at"] = now_ms
            msg.metadata = meta
        return candidates_tokens