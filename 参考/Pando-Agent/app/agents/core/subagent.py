import logging
import uuid
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple
from abc import ABC
from datetime import datetime
from app.infrastructure.llms.chat_models.schemes import TokenUsage
from ..bus.queues import MESSAGE_GATEWAY
from ..bus.types import InboundMessage, OutboundMessageType
from ..schemes import RuntimeContext
from ..sessions.compaction import SessionCompaction
from ..sessions.message import Message
from ..sessions.session import Session
from ..tools.factory import ToolsFactory
from ..tools.file_state import FileStateManager, FILE_STATE_MANAGER
from ..tools.policy import ToolPolicyResolver
from .base import AgentState, AgentMode
from .react import ReActAgent
from .run_abort import AbortReason


_LLM_ABORT_POLL_SEC = 0.2
SUB_AGENT_TYPE = "SubAgent"


class SubAgentManager(ABC):
    """SubAgent 管理器"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        channel_type: str,
        channel_id: str,
        parent_agent_type: str,
        workspace_path: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        **kwargs: Any,
    ):
        # 基本信息
        self.user_id = user_id
        self.parent_agent_type = parent_agent_type
        self.session_id = session_id
        self.channel_type = channel_type
        self.channel_id = channel_id
        self.workspace_path = workspace_path

        # 模型信息
        self.llm_provider = llm_provider or ""
        self.llm_model = llm_model or ""

        self.params = kwargs

        # 运行任务信息
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._parent_tool_names: List[str] = []
        self._parent_agent_config: Dict[str, Any] = {}

    def bind_parent_tools(self, tool_names: List[str], agent_config: Dict[str, Any]) -> None:
        """主 Agent 注册工具后同步当前可用工具名与配置（供 spawn 求交）。"""
        self._parent_tool_names = list(tool_names or [])
        self._parent_agent_config = dict(agent_config) if agent_config else {}

    def cancel_tasks(self) -> None:
        """父 Agent 中止时取消所有 async 子任务。"""
        for task in list(self._running_tasks.values()):
            if not task.done():
                task.cancel()

    async def start_task(
        self,
        task: str,
        run_ctx: RuntimeContext,
        *,
        mode: str = "sync",
        label: str | None = None,
    ) -> str:
        """
        启动子任务。sync 模式阻塞等待结果；async 模式后台执行并异步通知用户。
        """
        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")

        # 作业模式
        normalized_mode = (mode or "sync").strip().lower()
        if normalized_mode not in {"sync", "async"}:
            raise ValueError("spawn mode must be 'sync' or 'async'")

        # 同步 SubAgent 执行模式
        if normalized_mode == "sync":
            result = await self._run_subagent_task(
                task_id=task_id,
                task=task,
                label=display_label,
                run_ctx=run_ctx,
            )
            return self._format_subagent_result(task_id=task_id, label=display_label, result=result)
        else:
            # 异步SubAgent执行模式
            bg_task = asyncio.create_task(
                self._run_subagent_task(
                    task_id=task_id,
                    task=task,
                    label=display_label,
                    run_ctx=run_ctx,
                )
            )
            self._running_tasks[task_id] = bg_task
            bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))
            bg_task.add_done_callback(
                lambda t: asyncio.create_task(self._notify_async_result(task_id=task_id, label=display_label, fut=t))
            )
            logging.info("Started async subagent [%s]: %s", task_id, display_label)
            return f"Subagent [{display_label}] started asynchronously (id: {task_id})."

    async def _run_subagent_task(
        self,
        task_id: str,
        task: str,
        label: str,
        run_ctx: RuntimeContext,
    ) -> Dict[str, Any]:
        # 获取父 Agent 读记录中的规范化路径列表
        parent_actor = f"main:{self.session_id}" if self.session_id else "main:unknown"
        watch_paths = FILE_STATE_MANAGER.get_read_record_paths(parent_actor)
        started_at = time.time()

        # 创建并执行子 Agent
        try:
            subagent = SubAgent(
                user_id=self.user_id,
                session_id=self.session_id,
                channel_type=self.channel_type,
                channel_id=self.channel_id,
                parent_agent_type=self.parent_agent_type,
                parent_tool_names=self._parent_tool_names,
                parent_agent_config=self._parent_agent_config,
                parent_run_ctx=run_ctx,
                task_id=task_id,
                task=task,
                label=label,
                workspace_path=self.workspace_path,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                **self.params,
            )
        except ValueError as e:
            return {
                "task_id": task_id,
                "task": task,
                "status": False,
                "result": str(e) if "allowed_tool_names" in str(e) else (
                    "Subagent has no tools after policy intersection (check parent permissions and spawn deny list)."
                ),
            }
        result = await subagent.run()

        # 获取子 Agent 写记录中的规范化路径列表，提醒父 Agent 文件内容被子 Agent 修改过
        sibling_writes = FILE_STATE_MANAGER.get_write_records_since(parent_actor, started_at, watch_paths)
        reminder = FileStateManager.format_writes_since_reminder(sibling_writes)
        if reminder:
            body = (result.get("result") or "").strip()
            result["result"] = f"{body}\n\n{reminder}" if body else reminder

        return result

    async def _notify_async_result(self, task_id: str, label: str, fut: asyncio.Task) -> None:
        try:
            result = fut.result()
            content = self._format_subagent_result(task_id=task_id, label=label, result=result)
            inbound_msg = InboundMessage(
                channel_type=self.channel_type,
                channel_id=self.channel_id,
                user_id=self.user_id,
                session_id=self.session_id,
                agent_type=self.parent_agent_type,
                content=content,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                workspace_path=self.workspace_path,
                is_internal=True,
            )
            await MESSAGE_GATEWAY.push_inbound(inbound_msg)
        except asyncio.CancelledError:
            logging.info("Async subagent [%s] cancelled, skip completion notification", task_id)
        except Exception as e:
            content = self._format_subagent_result(
                task_id=task_id,
                label=label,
                result={"task_id": task_id, "task": "", "status": False, "result": f"Error: {e}"},
            )
            inbound_msg = InboundMessage(
                channel_type=self.channel_type,
                channel_id=self.channel_id,
                user_id=self.user_id,
                session_id=self.session_id,
                agent_type=self.parent_agent_type,
                content=content,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                workspace_path=self.workspace_path,
                is_internal=True,
            )
            await MESSAGE_GATEWAY.push_inbound(inbound_msg)

    @staticmethod
    def _format_subagent_result(task_id: str, label: str, result: Dict[str, Any]) -> str:
        status = "completed successfully" if result.get("status") else "failed"
        body = (result.get("result") or "").strip() or "(empty result)"
        return (
            f"[Subagent '{label}' {status}] (id: {task_id})\n\n"
            f"Task: {result.get('task') or ''}\n\n"
            f"Result:\n{body}"
        )


class SubAgent(ReActAgent):
    """SubAgent 执行类，属性仅在 __init__ 内通过 self 赋值。"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        channel_type: str,
        channel_id: str,
        parent_agent_type: str,
        parent_tool_names: List[str],
        parent_agent_config: Dict[str, Any],
        parent_run_ctx: RuntimeContext,
        task_id: str,
        task: str,
        label: str,
        workspace_path: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        **kwargs: Any,
    ):
        # 父 Agent 信息
        # super().__init__ 内会调用本类重载的 _init_tools_factory
        self.parent_agent_type = parent_agent_type
        self.parent_run_ctx = parent_run_ctx
        self._parent_tool_names = list(parent_tool_names or [])
        self._parent_agent_config = dict(parent_agent_config) if parent_agent_config else {}

        super().__init__(
            user_id=user_id,
            session_id=session_id,
            channel_type=channel_type,
            channel_id=channel_id,
            agent_type=SUB_AGENT_TYPE,
            workspace_path=workspace_path,
            llm_provider=llm_provider,
            llm_model=llm_model,
            **kwargs,
        )

        # 任务信息
        self.task_id = task_id
        self.task = task
        self.label = label

        # 历史消息（SubAgent 独立维护，不写入主会话）
        self.history_messages: List[Message] = []
        self.compaction: Optional[Message] = None
        self.last_compacted: int = 0

    # 重载父类方法（SubAgent 一次性实例，禁止 reset 清空 abort 状态）
    def reset(self):
        pass

    # ------------------------------------------------------------------
    # Abort相关操作
    # ------------------------------------------------------------------
    def is_aborted(self) -> bool:
        """本地中止或父 Agent 中止均视为应停止（sync spawn 随主 Agent 协作退出）。"""
        if self._abort_controller.is_aborted():
            return True
        
        # 获取父中断状态，传播主Agent中断状态
        parent = self.parent_run_ctx
        return parent is not None and parent.is_aborted()

    def _abort_reason_label(self) -> str:
        if self._abort_controller.is_aborted():
            return self._abort_controller.reason_label()
        
        # 获取父中断状态，传播主Agent中断原因
        parent = self.parent_run_ctx
        ctrl = parent.abort_controller if parent else None
        if ctrl is not None and ctrl.is_aborted():
            return ctrl.reason_label()
        return "aborted"

    # 重载父类方法
    def _init_subagent_context(self) -> None:
        '''
        Initialize subagent context
        '''
        self.subagent_manager = None
        self._agent_context.subagent_manager = None

    # 重载父类方法
    def _init_tools_factory(self) -> None:
        try:
            allowed_tool_names = ToolPolicyResolver.resolve_spawn_tools(
                parent_tool_names=self._parent_tool_names,
                parent_agent_config=self._parent_agent_config,
            )
            if not allowed_tool_names:
                raise ValueError("subagent allowed_tool_names is empty")
            self._available_tools = ToolsFactory.from_permissions(
                allowed_names=allowed_tool_names,
                ctx=self._agent_context,
            )
        except Exception as e:
            logging.error(f"Error in subagent tools registration: {str(e)}")
            raise e

    # 重载父类方法
    async def _build_prompt_and_question(self, question: str) -> str:
        """子 Agent 专用 system prompt：身份、当前时间、可用工具、workspace 路径（具体任务由 question 传入）。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        tool_names = ", ".join(sorted(self._available_tools.list_tool_names())) if self._available_tools else "(none)"
        self.system_prompt = f"""# Subagent

## Current Time
{now} ({tz})

You are a subagent spawned by the main agent to complete a specific task.

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings
5. Prefer tool use over speculation; verify key claims with concrete evidence
6. If blocked, state what failed, why, and the smallest next action needed
7. Only use tools listed under Available Tools

## Available Tools
{tool_names}

## What You Cannot Do
- Send messages directly to users
- Spawn other subagents
- Access the main agent's conversation history
- Use tools not listed above

## Output Contract
- Start with outcome status: Completed / Partially Completed / Blocked
- Then include: key findings, files/commands touched, and unresolved risks
- Keep raw logs minimal; summarize first and include only necessary details

## Agent Workspace
Your agent workspace is at: {self.workspace_path}

When done, return a structured, evidence-based summary aligned with the Output Contract."""
        return question

    # 重载父类方法
    async def _create_run_context(self) -> RuntimeContext:
        '''
        Create run context
        '''
        return RuntimeContext(
            actor_id=f"sub:{self.task_id}" if self.task_id else "sub:unknown",
            abort_controller=self.parent_run_ctx.abort_controller,   # 使用父Agent的中断控制器
            repo_id=self.parent_run_ctx.repo_id,
            params=dict(self.parent_run_ctx.params),
            notify_user_callback=self.parent_run_ctx.notify_user_callback,
            mcp_bridge=self._mcp_bridge,
        )

    async def run(self) -> Dict[str, Any]:
        """Run the agent

        Returns:
            result: Dict[str, Any]
        """
        # SubAgent 为一次性实例（spawn 时创建、run 结束即丢弃）
        # 设置运行状态
        self._state = AgentState.RUNNING
        self._stream_open = False
        content = ""
        try:
            self._mcp_bridge = await self._connect_mcp_tools()
            run_ctx = await self._create_run_context()

            # 构建提示词
            original_question = self.task
            question = await self._build_prompt_and_question(original_question)

            # 设置添加用户消息到 history 标志
            had_push_user_message = False
            context_overflow_recovered = False
            # ReAct 主循环：任一步 is_aborted() 为真则不再调度新一轮 think_and_act
            while self._current_step < self._max_steps and self._state != AgentState.FINISHED and not self.is_aborted():
                self._current_step += 1

                content, tool_calls, usage, tool_pairs = await self.think_and_act(question, run_ctx)
                # 如果用户消息未推送，则推送
                if not had_push_user_message:
                    await self.push_history_message(Message.user_message(original_question))
                    had_push_user_message = True
                # 如果工具调用，则推送工具调用消息
                if tool_calls:
                    await self.push_history_message(Message.tool_call_message(content, tool_calls=tool_calls))
                    for toolcall, tool_result in tool_pairs or []:
                        await self.push_history_message(
                            Message.tool_result_message(
                                f"{tool_result.result}",
                                toolcall.function.name,
                                toolcall.id,
                                metadata=getattr(tool_result, "metadata", None),
                            )
                        )
                    special_tool_calls = self._has_special_tools(tool_calls)
                    if special_tool_calls:
                        await self._handle_special_tool(special_tool_calls)
                else:
                    # 如果上下文溢出，则强制压缩上下文后，重新思考
                    if self.is_context_overflow_content(content) and not context_overflow_recovered:
                        await self.handle_context_overflow(usage, force=True)
                        context_overflow_recovered = True
                        continue
                    elif content:
                        await self.push_history_message(Message.assistant_message(content))
                        if self.agent_mode == AgentMode.GOAL and goal_reached:
                            question = "你已完成循环操作，请回头再看看你是否达到了目标。"
                            goal_reached = True
                            continue
                        else:
                            break
                        break

                # 如果已终止，不需要后面上下文判断与压缩
                if self.is_aborted():
                    break

                # 检查上下文是否溢出，需要压缩
                await self.handle_context_overflow(usage)

                # 检查模型是否进行死循环
                if await self.is_stuck():
                    self.handle_stuck_state()

                # 继续下一步
                question = "" #self.next_step_prompt

            # 检查是否达到最大步数
            if self._current_step >= self._max_steps and not self.is_aborted():
                self.request_abort(AbortReason.MAX_STEPS)

            # 统一异常处理
            if self.is_aborted():
                notice = f"Subagent aborted: {self._abort_reason_label()}."
                content = f"{content}\n\n{notice}" if content else notice

            return {
                "task_id": self.task_id,
                "label": self.label,
                "task": self.task,
                "status": not self.is_aborted(),
                "result": content,
            }
        except asyncio.CancelledError:
            return {
                "task_id": self.task_id,
                "label": self.label,
                "task": self.task,
                "status": False,
                "result": f"Subagent cancelled: {self._abort_reason_label()}.",
            }
        except Exception as e:
            self._state = AgentState.ERROR
            err = f"Error in agent execution: {str(e)}"
            await self.push_history_message(Message.assistant_message(err))
            return {
                "task_id": self.task_id,
                "label": self.label,
                "task": self.task,
                "status": False,
                "result": f"Subagent error: {err}.",
            }

    # 重载父类方法
    async def get_history_messages(self) -> List[Message]:
        """Get messages from local history"""
        return self.history_messages

    # 重载父类方法
    async def get_history_context(self) -> List[Dict[str, Any]]:
        return Session(
            session_id=self.session_id,
            agent_type=SUB_AGENT_TYPE,
            user_id=self.user_id,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            messages=self.history_messages,
            compaction=self.compaction,
            last_compacted=self.last_compacted,
        ).to_context()

    # 重载父类方法
    async def push_history_message(self, message: Message):
        """Add message to local history"""
        self.history_messages.append(message)

    # 重载父类方法
    async def notify_user(
        self,
        message: Optional[Message] = None,
        *,
        content: Optional[str] = None,
        outbound_type: OutboundMessageType = OutboundMessageType.RESPONSE,
    ) -> None:
        # SubAgent 不直接向用户推送消息
        pass

    # 重载父类方法
    async def handle_context_overflow(self, usage: TokenUsage, force: bool = False) -> None:
        if SessionCompaction.is_overflow(usage=usage, llm=self._last_llm) or force:
            await self._compact_history(keep_last_n=4)
        await self._prune_history()

    async def _compact_history(self, keep_last_n: int = 0) -> bool:
        if not self.history_messages or self._last_llm is None:
            return True
        compact_until = max(0, len(self.history_messages) - max(0, keep_last_n))
        start = self.last_compacted if (self.compaction is not None and self.last_compacted > 0) else 0
        if compact_until <= start:
            return True
        to_summarize = self.history_messages[start:compact_until]
        if not to_summarize:
            return True
        previous_summary = self.compaction.content if self.compaction is not None else ""
        summary_message = await SessionCompaction.compact(
            llm=self._last_llm,
            messages=to_summarize,
            previous_summary=previous_summary,
        )
        if summary_message is None or not (summary_message.content or "").strip():
            return False
        self.compaction = summary_message
        self.last_compacted = compact_until
        return True

    async def _prune_history(self) -> int:
        start = self.last_compacted if (self.compaction is not None and self.last_compacted > 0) else 0
        scan = self.history_messages[start:]
        return SessionCompaction.prune(scan)

    # 重载父类方法
    async def consolidate_memory(self) -> None:
        '''
        Consolidate memory
        '''
        # SubAgent 不写入长期记忆
        pass
