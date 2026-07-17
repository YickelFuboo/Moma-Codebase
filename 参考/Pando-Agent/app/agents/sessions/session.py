from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .message import Message


class Session(BaseModel):
    """会话数据模型：仅负责会话元数据与消息列表，不包含压缩逻辑。"""

    session_id: str
    description: Optional[str] = None
    agent_type: str
    channel_type: str = ""
    user_id: str

    llm_provider: str
    llm_model: str = "default"
    workspace_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_internal: bool = False

    # 会话历史信息
    messages: List[Message] = Field(default_factory=list)  # 原始历史会话记录

    # 长期记忆提取信息
    last_consolidated: int = 0  # 已被“长期记忆提取”处理过的消息数量（用于记忆流水线）

    # 会话压缩信息
    compaction: Optional[Message] = None  # 最新压缩摘要消息
    last_compacted: int = 0  # 已被“会话压缩”覆盖的 messages 数量（to_context 从此处开始取）

    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    def is_internal_session(self) -> bool:
        """内部派生 session，不应出现在用户侧历史列表。"""
        return self.is_internal

    def clear(self) -> None:
        """清空会话历史。"""
        self.messages.clear()
        self.last_consolidated = 0
        self.compaction = None
        self.last_compacted = 0
        self.last_updated = datetime.now()
    
    def to_context(self, max_messages: int = 500) -> List[Dict[str, Any]]:
        """返回供 LLM 使用的会话上下文。

        规则：
        - 若存在 compaction 摘要，则优先使用“最新摘要 + last_compacted 之后的消息”；
        """
        PRUNED_PLACEHOLDER = "[Old tool result content cleared]"

        def _to_pruned_message(m: Message) -> Dict[str, Any]:
            if m.is_tool_result and isinstance(m.metadata, dict) and m.metadata.get("pruned_at"):
                ctx = m.to_context()
                ctx["content"] = PRUNED_PLACEHOLDER
                return ctx
            return m.to_context()

        if self.compaction is not None and self.last_compacted > 0:
            tail = self.messages[self.last_compacted:]
            sliced = tail[-max_messages:]
            summary = self.compaction.to_context()
            return [summary] + [_to_pruned_message(m) for m in sliced]
        sliced = self.messages[-max_messages:]
        return [_to_pruned_message(m) for m in sliced]

    def to_information(self) -> Dict[str, Any]:
        """会话关键信息，供 API 列表等使用。"""
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "channel_type": self.channel_type,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "description": self.description,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "workspace_path": self.workspace_path,
            "metadata": self.metadata,
            "is_internal": self.is_internal,
        }

    def model_dump(self) -> Dict[str, Any]:
        """序列化。"""
        return {
            "session_id": self.session_id,
            "description": self.description,
            "agent_type": self.agent_type,
            "channel_type": self.channel_type,
            "user_id": self.user_id,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "workspace_path": self.workspace_path,
            "metadata": self.metadata,
            "is_internal": self.is_internal,
            "messages": [msg.model_dump() for msg in self.messages],
            "last_consolidated": self.last_consolidated,
            "compaction": (self.compaction.model_dump() if self.compaction is not None else None),
            "last_compacted": self.last_compacted,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }