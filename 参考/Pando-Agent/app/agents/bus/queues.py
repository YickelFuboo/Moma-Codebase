import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from .types import InboundMessage, OutboundMessage, OutboundMessageType, AgentEntry
from ..core.run_abort import AbortReason
from app.config.settings import settings
from app.utils.common import exc_summary


# Agent 池相关配置
AGENT_POOL_IDLE_TTL_SEC = 120
AGENT_POOL_CLEANUP_INTERVAL_SEC = 30

# 消息池相关配置
SESSION_MAILBOX_MAXSIZE = 50
SESSION_IDLE_TTL_SEC = 1800
GLOBAL_RUN_CONCURRENCY = 32
ChannelOutboundCallback = Callable[[OutboundMessage], None]
CHANNEL_OUTBOUND_CALLBACKS: Dict[str, ChannelOutboundCallback] = {}

AgentPoolKey = Tuple[str, str, str, str, str, str]


def _make_agent_pool_key(
    agent_type: str,
    user_id: str,
    session_id: str,
    channel_type: str,
    channel_id: str,
    workspace_path: str,
) -> AgentPoolKey:
    return (agent_type, user_id, session_id, channel_type, channel_id, workspace_path)


class MessageBus:
    def __init__(self):
        self._task: Optional[asyncio.Task[None]] = None
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        # session mailbox/worker 模型：同一 session 串行、不同 session 并行
        # - session_mailboxes: 每个 session 一个收件箱（队列），同 session 的 inbound 先进入该队列
        # - _session_workers: 每个 session 一个 worker 协程任务，循环消费 mailbox 并执行（天然串行）
        # - _session_last_active_at: 记录 session 最近一次收到消息的时间，用于 idle TTL 回收资源
        # - _session_lock: 保护上述 dict 的并发读写，避免并发分发时重复创建 mailbox/worker
        self.session_mailboxes: Dict[str, asyncio.Queue[InboundMessage]] = {}  # key是session_id，value是asyncio.Queue[InboundMessage]
        self._session_workers: Dict[str, asyncio.Task] = {}  # key是session_id，value是asyncio.Task
        self._session_run_tasks: Dict[str, asyncio.Task] = {}  # 当前 session 正在执行的 agent.run 任务
        self._session_last_active_at: Dict[str, float] = {}  
        self._session_lock = asyncio.Lock()
        self._global_run_semaphore = asyncio.Semaphore(GLOBAL_RUN_CONCURRENCY)

        # Agent 池：
        self.running_agent_pool: Dict[str, Any] = {}  # key是session_id，value是agent
        self.free_agent_pool: Dict[AgentPoolKey, List[AgentEntry]] = {}
        self._agent_pool_lock = asyncio.Lock()

    async def push_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)

    async def pop_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def push_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)

    async def pop_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    async def pop_outbound_by_session_id(self, session_id: str) -> OutboundMessage:
        """只消费指定 session_id 的下一条出站消息（不匹配的放回队列末尾，阻塞直到有该 session 的消息）。"""
        while True:
            outbound_msg = await self.pop_outbound()
            if outbound_msg.session_id == session_id:
                return outbound_msg
            await self.outbound.put(outbound_msg)
    
    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

    @property
    def running_agent_count(self) -> int:
        """当前运行中的 Agent 数量。"""
        return len(self.running_agent_pool)
    
    async def _get_status_text(self, session_id: Optional[str] = None) -> str:
        """生成 /status 的回复文案；持 _session_lock 快照 session_mailboxes，避免遍历时 dict 被并发修改。"""
        in_cnt = self.inbound_size
        out_cnt = self.outbound_size
        run_cnt = self.running_agent_count
        current_session_run_cnt = 1 if (session_id and session_id in self.running_agent_pool) else 0
        mailbox_total = 0
        current_session_pending_cnt = 0
        async with self._session_lock:
            snapshot = list(self.session_mailboxes.items())
        for sid, q in snapshot:
            n = q.qsize()
            mailbox_total += n
            if session_id and sid == session_id:
                current_session_pending_cnt = n
        lines = [
            "**消息总线状态**",
            f"- in 通道待处理: {in_cnt}",
            f"- out 通道待处理: {out_cnt}",
            f"- 所有会话 in 通道待处理: {mailbox_total}",
            f"- 当前会话 in 通道待处理: {current_session_pending_cnt}",
            f"- 运行态 Agent 数量: {run_cnt}",
            f"- 当前会话运行态 Agent 数量: {current_session_run_cnt}",
        ]
        return "\n".join(lines)

    async def run(self) -> None:
        """Run the message bus：inbound、outbound 与 Agent 池清理三路并发。"""
        await asyncio.gather(
            self._run_inbound_loop(),
            self._run_outbound_loop(),
            self._run_agent_pool_cleanup_loop(),
        )

    def start(self) -> None:
        """启动消息网关后台任务。"""
        if self._task is not None and not self._task.done():
            logging.warning("Message gateway already running")
            return
        self._task = asyncio.create_task(self.run(), name="message_gateway")

    async def stop(self) -> None:
        """停止并等待消息网关后台任务退出。"""
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            if self._task is task:
                self._task = None

    async def _run_inbound_loop(self) -> None:
        """循环消费 inbound：系统命令(/status、/stop)直接处理不排队；其余按 session 入 mailbox 串行执行。"""
        while True:
            inbound_msg = await self.pop_inbound()
            if not inbound_msg:
                continue
            
            # 系统命令直接处理不排队
            content_stripped = (inbound_msg.content or "").strip()
            if content_stripped == "/status":
                status_text = await self._get_status_text(session_id=inbound_msg.session_id)
                await self.push_outbound(OutboundMessage(
                    channel_type=inbound_msg.channel_type,
                    channel_id=inbound_msg.channel_id,
                    user_id=inbound_msg.user_id,
                    session_id=inbound_msg.session_id,
                    content=status_text,
                ))
                continue
            if content_stripped == "/stop":
                session_id = inbound_msg.session_id
                agent = self.running_agent_pool.get(session_id)
                async with self._session_lock:
                    run_task = self._session_run_tasks.get(session_id)
                if agent and run_task and not run_task.done():
                    agent.request_abort(AbortReason.USER_INTERRUPT)
                    await self._finish_run_after_abort(session_id, agent, run_task)
                    reply = "已停止当前任务。"
                else:
                    reply = "当前没有正在运行的任务。"
                await self.push_outbound(OutboundMessage(
                    channel_type=inbound_msg.channel_type,
                    channel_id=inbound_msg.channel_id,
                    user_id=inbound_msg.user_id,
                    session_id=inbound_msg.session_id,
                    content=reply,
                ))
                continue
            if content_stripped == "/kill":
                session_id = inbound_msg.session_id
                agent = self.running_agent_pool.get(session_id)
                async with self._session_lock:
                    run_task = self._session_run_tasks.get(session_id)
                if agent and run_task and not run_task.done():
                    agent.request_abort(AbortReason.TASK_CANCELLED)
                    await self._finish_run_after_abort(session_id, agent, run_task, grace_sec=0)
                    reply = "已强制终止当前任务。"
                else:
                    reply = "当前没有正在运行的任务。"
                await self.push_outbound(OutboundMessage(
                    channel_type=inbound_msg.channel_type,
                    channel_id=inbound_msg.channel_id,
                    user_id=inbound_msg.user_id,
                    session_id=inbound_msg.session_id,
                    content=reply,
                ))
                continue

            # 处理Agent对话消息
            try:
                await self._dispatch_inbound(inbound_msg)
            except Exception as e:
                logging.exception("MessageBus process inbound failed: %s", e)
                try:
                    await self.push_outbound(OutboundMessage(
                        channel_type=inbound_msg.channel_type,
                        channel_id=inbound_msg.channel_id,
                        user_id=inbound_msg.user_id,
                        session_id=inbound_msg.session_id,
                        content=f"Error: {e!s}",
                    ))
                except Exception as push_err:
                    logging.warning("Failed to push error outbound: %s", push_err)

    async def _dispatch_inbound(self, inbound_msg: InboundMessage) -> None:
        session_id = inbound_msg.session_id
        if not session_id:
            raise ValueError("Session ID is required")

        # 获取会话mailbox
        async with self._session_lock:
            mailbox = self.session_mailboxes.get(session_id)
            if mailbox is None:
                mailbox = asyncio.Queue(maxsize=SESSION_MAILBOX_MAXSIZE)
                self.session_mailboxes[session_id] = mailbox
            self._session_last_active_at[session_id] = asyncio.get_running_loop().time()

            # 若没有运行中的会话worker，则创建
            worker = self._session_workers.get(session_id)
            if worker is None or worker.done():                
                self._session_workers[session_id] = asyncio.create_task(self._run_session_worker(session_id))
            
            # 如果启用消息中断，新消息来则强制设置当前运行中的Agent，等正式停止后处理mailBox中下一条消息用户消息；
            # internal（如 async SubAgent 完成回调）仅排队，不 SUPERSEDED
            if settings.enable_message_interrupt and not inbound_msg.is_internal:
                running_agent = self.running_agent_pool.get(session_id)
                if running_agent:
                    running_agent.request_abort(AbortReason.SUPERSEDED)
                    logging.info("Inbound abort (superseded): session_id=%s", session_id)
            
            # 队列满则挤出最早消息
            if mailbox.full():
                try:
                    mailbox.get_nowait()
                except Exception:
                    pass
            try:
                mailbox.put_nowait(inbound_msg)
            except asyncio.QueueFull:
                try:
                    mailbox.get_nowait()
                except Exception:
                    pass
                mailbox.put_nowait(inbound_msg)

    async def _run_session_worker(self, session_id: str) -> None:
        # 逐条处理当前session_id的mailbox中的消息
        while True:
            mailbox = self.session_mailboxes.get(session_id)
            if mailbox is None:
                return
            try:
                msg = await asyncio.wait_for(mailbox.get(), timeout=SESSION_IDLE_TTL_SEC)
            except asyncio.TimeoutError:
                async with self._session_lock:
                    last_active_at = self._session_last_active_at.get(session_id)
                    now = asyncio.get_running_loop().time()
                    if last_active_at is None or now - last_active_at >= SESSION_IDLE_TTL_SEC:
                        self.session_mailboxes.pop(session_id, None)
                        self._session_last_active_at.pop(session_id, None)
                        self._session_workers.pop(session_id, None)
                        return
                continue
            try:
                async with self._global_run_semaphore:
                    await self._handle_inbound(msg)  # Agent处理完，继续处理下一轮
            except Exception as e:
                logging.exception(
                    "Session worker failed: session_id=%s origin=%s",
                    session_id,
                    exc_summary(e),
                )
                try:
                    await self.push_outbound(OutboundMessage(
                        channel_type=msg.channel_type,
                        channel_id=msg.channel_id,
                        user_id=msg.user_id,
                        session_id=msg.session_id,
                        content=f"Error: {e!s}",
                    ))
                    await self.push_outbound(OutboundMessage(
                        channel_type=msg.channel_type,
                        channel_id=msg.channel_id,
                        user_id=msg.user_id,
                        session_id=msg.session_id,
                        content="",
                        outbound_type=OutboundMessageType.RUN_END,
                    ))
                except Exception:
                    pass

    async def _handle_inbound(self, inbound_msg: InboundMessage) -> None:
        """处理单条 inbound：更新 session + 复用/创建 agent 执行（系统命令已在 _run_inbound_loop 直接处理，不进入此处）。"""
        from ..sessions.manager import SESSION_MANAGER
        from ..contants import is_planning_agent_type
        from ..plan.planning import PlanningAgent
        from ..core.react import ReActAgent

        session_id = inbound_msg.session_id
        if not session_id:
            raise ValueError("Session ID is required")

        session = await SESSION_MANAGER.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        workspace_path = inbound_msg.workspace_path
        inbound_metadata = dict(inbound_msg.metadata) if inbound_msg.metadata else {}
        await SESSION_MANAGER.update_session(
            session_id,
            description=session.description if session.description else (inbound_msg.content or "")[:20],
            channel_type=inbound_msg.channel_type,
            agent_type=inbound_msg.agent_type,
            llm_provider=inbound_msg.llm_provider,
            llm_model=inbound_msg.llm_model,
            workspace_path=workspace_path,
            metadata=inbound_metadata or None,
        )

        agent_type = inbound_msg.agent_type
        agent = await self._acquire_agent_from_pool(
            agent_type=agent_type,
            session_id=session_id,
            channel_type=inbound_msg.channel_type,
            channel_id=inbound_msg.channel_id,
            user_id=inbound_msg.user_id,
            llm_provider=inbound_msg.llm_provider or "",
            llm_model=inbound_msg.llm_model or "",
            workspace_path=workspace_path,
            metadata=inbound_metadata,
        )
        if agent is None:
            agent_kwargs = dict(
                user_id=inbound_msg.user_id,
                session_id=session_id,
                channel_type=inbound_msg.channel_type,
                channel_id=inbound_msg.channel_id,
                agent_type=agent_type,
                llm_provider=inbound_msg.llm_provider,
                llm_model=inbound_msg.llm_model,
                workspace_path=workspace_path,
                **inbound_metadata,
            )
            if is_planning_agent_type(agent_type):
                agent = PlanningAgent(**agent_kwargs)
            else:
                agent = ReActAgent(**agent_kwargs)

        run_task: Optional[asyncio.Task] = None
        try:
            self.running_agent_pool[session_id] = agent
            run_task = asyncio.create_task(
                agent.run(inbound_msg.content or "", is_internal=bool(inbound_msg.is_internal)),
                name=f"agent_run:{session_id}",
            )
            async with self._session_lock:
                self._session_run_tasks[session_id] = run_task
            await run_task
        finally:
            async with self._session_lock:
                self._session_run_tasks.pop(session_id, None)
            self.running_agent_pool.pop(session_id, None)
            await self._add_agent_to_free_pool(agent)

    async def _finish_run_after_abort(
        self,
        session_id: str,
        agent: Any,
        run_task: asyncio.Task,
        grace_sec: Optional[int] = None,
    ) -> None:
        """/stop：先等 agent_run_hard_kill_grace_sec 协作退出，再 cancel；/kill 传 grace_sec=0 立即 cancel。"""
        grace = settings.agent_run_hard_kill_grace_sec if grace_sec is None else grace_sec
        if grace > 0 and not run_task.done():
            try:
                await asyncio.wait_for(run_task, timeout=grace)
                return
            except asyncio.TimeoutError:
                pass
        # 如果协作已退出，直接返回
        if run_task.done():
            return
        # 如果协作未退出，立即取消
        logging.warning("Hard kill agent run: session_id=%s", session_id)
        run_task.cancel()
        try:
            await asyncio.wait_for(run_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception as e:
            logging.warning("Hard kill await run_task failed: session_id=%s %s", session_id, exc_summary(e))
        if not run_task.done():
            try:
                agent.reset()
            except Exception as e:
                logging.warning("Hard kill agent.reset failed: session_id=%s %s", session_id, exc_summary(e))

    async def _run_outbound_loop(self) -> None:
        """循环消费 outbound，按 channel_type 回调发送。"""
        while True:
            outbound_msg = await self.pop_outbound()
            callback = CHANNEL_OUTBOUND_CALLBACKS.get(outbound_msg.channel_type)
            if callback:
                callback(outbound_msg)
            else:
                logging.warning("No outbound callback for channel_type=%s", outbound_msg.channel_type)
    
    async def _acquire_agent_from_pool(
        self, agent_type: str, session_id: str, channel_type: str, channel_id: str,
        user_id: str, llm_provider: str, llm_model: str,
        workspace_path: Optional[str],
        metadata: dict[str, Any],
    ) -> Optional[Any]:
        """池键含 session_id + 解析后的 workspace_path。"""
        from ..contants import resolve_workspace_path

        ws = resolve_workspace_path(user_id, agent_type, workspace_path)
        pool_key = _make_agent_pool_key(
            agent_type,
            user_id,
            session_id,
            channel_type,
            channel_id,
            str(ws),
        )
        async with self._agent_pool_lock:
            entries = self.free_agent_pool.get(pool_key, [])
            if not entries:
                return None
            entry = entries.pop(0)
            agent = entry.agent
            agent.llm_provider = llm_provider or (agent.llm_provider or "")
            agent.llm_model = llm_model or (agent.llm_model or "")
            if metadata:
                agent.params.update(metadata)
                agent._agent_context.params.update(metadata)
            agent.reset()
            return agent

    async def _add_agent_to_free_pool(self, agent: Any) -> None:
        """按当前 agent 新建 AgentEntry 并加入 free_agent_pool（复用与新建统一走此逻辑）。"""
        entry = AgentEntry(
            agent=agent,
            last_used_at=asyncio.get_running_loop().time(),
        )
        pool_key = _make_agent_pool_key(
            agent.agent_type,
            agent.user_id,
            agent.session_id,
            agent.channel_type,
            agent.channel_id,
            str(agent.workspace_path),
        )
        async with self._agent_pool_lock:
            if pool_key not in self.free_agent_pool:
                self.free_agent_pool[pool_key] = []
            self.free_agent_pool[pool_key].append(entry)

    async def _run_agent_pool_cleanup_loop(self) -> None:
        """定期清理 free_agent_pool 中超过 AGENT_POOL_IDLE_TTL_SEC 未复用的 Agent。"""
        while True:
            await asyncio.sleep(AGENT_POOL_CLEANUP_INTERVAL_SEC)
            now = asyncio.get_running_loop().time()
            async with self._agent_pool_lock:
                for pool_key in list(self.free_agent_pool.keys()):
                    entries = self.free_agent_pool[pool_key]
                    kept = [e for e in entries if (now - e.last_used_at) <= AGENT_POOL_IDLE_TTL_SEC]
                    self.free_agent_pool[pool_key] = kept
                    if not kept:
                        self.free_agent_pool.pop(pool_key, None)

MESSAGE_GATEWAY = MessageBus()

def start_message_gateway() -> None:
    """启动消息网关。"""
    MESSAGE_GATEWAY.start()

async def stop_message_gateway() -> None:
    """停止消息网关。"""
    await MESSAGE_GATEWAY.stop()