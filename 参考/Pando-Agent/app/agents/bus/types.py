from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class OutboundMessageType(str, Enum):
    """出站消息类型：与 WebSocket message_type 对齐。"""

    RESPONSE = "response"
    STREAM_START = "stream_start"
    STREAM_DELTA = "stream_delta"
    STREAM_END = "stream_end"
    RUN_END = "run_end"


@dataclass
class InboundMessage:
    """Message received from a chat channel."""
    agent_type: str
    channel_type: str  # telegram, discord, slack, whatsapp
    channel_id: str  # Channel identifier
    session_id: str  # Session identifier
    user_id: str  # User identifier
    content: str  # Message text
    llm_provider: str = ""
    llm_model: str = ""
    workspace_path: Optional[str] = None
    is_internal: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""
    channel_type: str
    channel_id: str
    user_id: str
    session_id: str
    content: str
    outbound_type: OutboundMessageType = OutboundMessageType.RESPONSE
    media: list[str] = field(default_factory=list)  # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data


@dataclass
class AgentEntry:
    """池条目：实例 + 最后复用时间（类型用 agent.agent_type，运行态由 running_agent_pool 表示）。"""
    agent: Any
    last_used_at: float = 0.0
