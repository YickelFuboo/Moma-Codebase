import json
import asyncio
import logging
import re
from abc import ABC
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.infrastructure.llms.chat_models.schemes import TokenUsage
from ..contants import AGENT_CONFIG_DIR, AGENT_CONFIG_FILE, resolve_workspace_path
from ..skills.manager import SkillsManager
from .run_abort import AbortReason, RunAbortController
from ..bus.types import OutboundMessage, OutboundMessageType
from ..bus.queues import MESSAGE_GATEWAY
from ..sessions.manager import SESSION_MANAGER
from ..sessions.message import Role, Message
from ..schemes import AgentContext
from ..sessions.compaction import SessionCompaction
from app.config.settings import settings


class AgentState(str, Enum):
    """Agent state enumeration"""
    IDLE = "IDLE"  # Idle state
    RUNNING = "RUNNING"  # Running state
    WAITING = "WAITING"  # Waiting for user input
    ERROR = "ERROR"  # Error state
    FINISHED = "FINISHED"  # Finished state

class ToolChoice(str, Enum):
    """工具调用模式：none=不暴露工具，auto=由模型决定，required=必须调用工具。"""
    NONE = "none"
    AUTO = "auto"
    REQUIRED = "required"

class AgentMode(str, Enum):
    """Agent mode enumeration"""
    DEFAULT = "default"
    GOAL = "goal"


class BaseAgent(ABC):
    """Base Agent class

    Base class for all agents, defining basic properties and methods.
    执行类，不参与 schema 序列化，仅用 __init__ 内 self 赋值。
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        channel_type: str,
        channel_id: str,
        agent_type: str,
        workspace_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        next_step_prompt: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        **kwargs: Any,
    ):
        # 会话与用户
        self.session_id = session_id
        self.user_id = user_id

        # 客户端信息
        self.channel_type = channel_type
        self.channel_id = channel_id

        # 基本信息
        self.agent_type = agent_type
        self.agent_description: str = ""
        self.agent_mode = AgentMode.DEFAULT
        self.agent_path = AGENT_CONFIG_DIR / self.agent_type

        # 会话/运行时指定模型
        self.llm_provider = str(llm_provider or "").strip()
        self.llm_model = str(llm_model or "").strip()

        # 提示词信息
        self.system_prompt = system_prompt or "You are pando, a helpful assistant."
        self.user_prompt = user_prompt or ""
        self.next_step_prompt = next_step_prompt or "Please continue your work."

        # 工作空间（用户指定路径或默认沙箱）
        self.workspace_path = resolve_workspace_path(
            self.user_id,
            self.agent_type,
            workspace_path,
        )

        # 执行步数相关
        self._state = AgentState.IDLE
        self._current_step = 0
        self._max_steps = 50  # 默认最大步数
        self._max_duplicate_steps = 2   # 默认最大重复次数，用于检验当前项agent是否挂死
        self._memory_window = 100

        # 扩展参数        
        self.params = dict(kwargs)
        
        # 执行过程信息
        self._stream_open = False
        self._last_llm: Any = None

        # 加载配置
        self.agent_config: dict = {}
        self._load_agent_config()

        # 成员变量
        self._abort_controller = RunAbortController()  # 异常控制（Agent 生命周期内复用，每轮 run 通过 clear 复位）
        self._memory_manager = None
        
        # 上下文
        self._agent_context = AgentContext(
            user_id=self.user_id,
            session_id=self.session_id,
            agent_type=self.agent_type,
            agent_description=self.agent_description,
            agent_path=str(self.agent_path),
            workspace_path=str(self.workspace_path),
            channel_type=self.channel_type,
            channel_id=self.channel_id,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            skills_manager=self.skills_manager,
            params=self.params,
        )

    # ------------------------------------------------------------------
    # Reset相关操作
    # ------------------------------------------------------------------
    def reset(self):
        """重置 agent 状态到初始状态
        
        重置以下内容：
        - 状态设置为 IDLE
        - 当前步数归零
        - Abort 状态复位（供池复用 / busy 重置等路径兜底）
        """
        try:
            self._state = AgentState.IDLE
            self._current_step = 0
            self._abort_controller.clear()
            self._stream_open = False
            self._last_llm: Any = None
        except Exception as e:
            logging.error(f"Error in agent reset: {str(e)}")
            raise e

    # ------------------------------------------------------------------
    # Abort相关操作
    # ------------------------------------------------------------------
    def request_abort(self, reason: AbortReason, message: Optional[str] = None) -> None:
        """请求终止当前 run（用户中断、抢占、错误等多入口统一入口）。"""
        self._abort_controller.request_abort(reason, message)

    def is_aborted(self) -> bool:
        return self._abort_controller.is_aborted()

    def _abort_reason_label(self) -> str:
        if self._abort_controller.is_aborted():
            return self._abort_controller.reason_label()
        return "aborted"

    # ------------------------------------------------------------------
    # Load相关操作
    # ------------------------------------------------------------------
    def _load_agent_config(self) -> None:
        """加载 agent 目录下 config.json，填充 agent_config 与 description。"""
        cfg_path = self.agent_path / AGENT_CONFIG_FILE
        self.agent_config = {}
        if cfg_path.is_file():
            try:
                raw = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.agent_config = raw
            except Exception as e:
                logging.warning("Failed to load %s: %s", cfg_path, e)
        self.agent_description = (self.agent_config.get("description_en") or "").strip()

        self._load_agent_mode()
        self._load_llms_config()
        self._load_skills_config()

    def _load_agent_mode(self) -> None:
        """从根级 modes 读取当前 mode 及运行参数。"""
        modes_cfg = self.agent_config.get("modes")
        if not isinstance(modes_cfg, dict):
            return

        mode_key = modes_cfg.get("mode")
        if mode_key:
            self.agent_mode = AgentMode(str(mode_key).strip().lower())

        mode_params = modes_cfg.get(self.agent_mode.value)
        if not isinstance(mode_params, dict):
            return
        if "max_steps" in mode_params:
            self._max_steps = mode_params["max_steps"]
        if "max_duplicate_steps" in mode_params:
            self._max_duplicate_steps = mode_params["max_duplicate_steps"]
        if "memory_window" in mode_params:
            self._memory_window = mode_params["memory_window"]

    def _load_llms_config(self) -> None:
        """加载模型配置"""
        self.llms_list = []
        llm_cfg = self.agent_config.get("llm")
        if isinstance(llm_cfg, dict):
            for key in ("primary", "fallback"):
                item = llm_cfg.get(key)
                if isinstance(item, dict):
                    pair = (
                        str(item.get("provider") or "").strip(),
                        str(item.get("model") or "").strip(),
                    )
                    if pair != ("", "") and pair not in self.llms_list:
                        self.llms_list.append(pair)
        if self.llm_provider or self.llm_model:
            pair = (self.llm_provider, self.llm_model)
            self.llms_list = [pair] + [x for x in self.llms_list if x != pair]
        if not self.llms_list:
            self.llms_list = [("", "")]

    def _load_skills_config(self) -> None:
        """从 agent_config 的 skills.permissions / skills.allow_manage 读取。"""
        skill_names: list[str] = []
        allow_manage = False
        external_dirs: list[str] = []

        data = self.agent_config
        if isinstance(data, dict):
            skills = data.get("skills")
            if isinstance(skills, dict):
                perm = skills.get("permissions")
                if isinstance(perm, dict):
                    skill_names = [
                        str(name)
                        for name, decision in perm.items()
                        if str(decision).strip().lower() == "allow"
                    ]
                allow_manage = str(skills.get("allow_manage", "no")).strip().lower() == "yes"
                raw_ext = skills.get("external_dirs")
                if isinstance(raw_ext, list):
                    external_dirs = [str(x).strip() for x in raw_ext if str(x).strip()]

        self.skills_manager = SkillsManager(
            self.agent_type,
            filter_skills=skill_names or None,
            allow_manage=allow_manage,
            external_dirs=external_dirs or None,
            workspace_path=self.workspace_path,
        )

    # ------------------------------------------------------------------
    # Run相关操作
    # ------------------------------------------------------------------
    async def run(self, question: str) -> str:
        """Run the agent
        
        Args:
            question: Input question
            
        Returns:
            str: Execution result
        """
        pass
 
    def handle_stuck_state(self):
        """Handle stuck state by adding a prompt to change strategy"""
        stuck_prompt = "\
        Observed duplicate responses. Consider new strategies and avoid repeating ineffective paths already attempted."
        self.next_step_prompt = f"{stuck_prompt}\n{self.next_step_prompt}"
        logging.warning(f"Agent detected stuck state. Added prompt: {stuck_prompt}")

    async def is_stuck(self) -> bool:
        """Check if the agent is stuck in a loop by detecting duplicate content"""
        history = await self.get_history_messages()
        if len(history) < 2:
            return False

        last_message = history[-1]
        if not last_message.content:
            return False

        # Count identical content occurrences
        duplicate_count = sum(
            1
            for msg in reversed(history[:-1])
            if msg.role == Role.ASSISTANT and msg.content == last_message.content
        )

        return duplicate_count >= self._max_duplicate_steps

    def get_state(self) -> AgentState:
        """Get current state
        
        Returns:
            AgentState: Current state
        """
        return self._state
    
    def _strip_think(self, text: str | None) -> str | None:
        """去掉回复中的 <think>...</think> 块（部分思考模型会内嵌），避免把思考过程当正文返回。"""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    # ------------------------------------------------------------------
    # 会话历史相关操作
    # ------------------------------------------------------------------
    async def get_history_messages(self) -> List[Message]:
        """Get messages from session"""
        return await SESSION_MANAGER.get_messages(self.session_id)

    async def get_history_context(self) -> List[Dict[str, Any]]:
        """Get history for context"""
        return await SESSION_MANAGER.get_context(self.session_id)

    async def push_history_message(self, message: Message):
        """Add message to session and push user"""
        # 记录会话历史
        await SESSION_MANAGER.add_message(self.session_id, message)

    async def notify_user(
        self,
        message: Optional[Message] = None,
        *,
        content: Optional[str] = None,
        outbound_type: OutboundMessageType = OutboundMessageType.RESPONSE,
    ) -> None:
        """经 MessageBus 通知用户；outbound_type 区分 response、流式 start/delta/end、整轮 run_end。"""
        if outbound_type == OutboundMessageType.STREAM_START:
            if self._stream_open:
                return
            self._stream_open = True
            text = ""
        elif outbound_type == OutboundMessageType.STREAM_DELTA:
            text = content if content is not None else (message.to_user_message().get("content", "") if message else "")
            if not text:
                return
            if not self._stream_open:
                self._stream_open = True
                await MESSAGE_GATEWAY.push_outbound(OutboundMessage(
                    channel_type=self.channel_type,
                    channel_id=self.channel_id,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    content="",
                    outbound_type=OutboundMessageType.STREAM_START,
                ))
        elif outbound_type == OutboundMessageType.STREAM_END:
            if not self._stream_open:
                return
            self._stream_open = False
            text = ""
        elif outbound_type == OutboundMessageType.RUN_END:
            text = ""
        else:
            if message is not None:
                text = message.to_user_message().get("content", "")
            else:
                text = content or ""

        await MESSAGE_GATEWAY.push_outbound(OutboundMessage(
            channel_type=self.channel_type,
            channel_id=self.channel_id,
            user_id=self.user_id,
            session_id=self.session_id,
            content=text,
            outbound_type=outbound_type,
        ))

    async def push_history_message_and_notify_user(self, message: Message):
        """Add message to session and push user"""
        await self.push_history_message(message)
        #if message.tool_call_id is None: # 显示工具调用结果消息不通知用户
        await self.notify_user(message)

    # ------------------------------------------------------------------
    # 上下文溢出相关操作
    # ------------------------------------------------------------------
    def is_context_overflow_content(self, content: str) -> bool:
        if not content:
            return False
        return "context_overflow" in content.lower()

    async def handle_context_overflow(self, usage: TokenUsage, force: bool = False) -> None:
        # 压缩搜段1：清理旧的历史内容进行摘要
        if SessionCompaction.is_overflow(usage=usage, llm=self._last_llm) or force: # force为True时，强制压缩
            await SESSION_MANAGER.compact_session(
                self.session_id,
                keep_last_n=max(6, settings.compaction_keep_last_n),
            )
        # 压缩搜段2：清理旧的tool result消息
        await SESSION_MANAGER.prune_session(self.session_id)

    # ------------------------------------------------------------------
    # 记忆合并相关操作
    # ------------------------------------------------------------------
    async def consolidate_memory(self) -> None:
        '''
        Consolidate memory
        '''
        def _on_consolidate_done(task: asyncio.Task) -> None:
            try:
                task.result()
            except Exception as e:
                logging.warning("Memory consolidate_memory (background) failed: %s", e)
        asyncio.create_task(self._memory_manager.consolidate_memory(llm=self._last_llm)).add_done_callback(_on_consolidate_done)