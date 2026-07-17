import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from .base import AgentState, BaseAgent, ToolChoice, AgentMode
from .run_abort import AbortReason
from ..tools.factory import ToolsFactory
from ..tools.policy import ToolPolicyResolver
from ..tools.scheduler import ToolRunNotifier, ToolScheduleSession
from ..sessions.message import Message, ToolCall, Function
from app.infrastructure.llms.chat_models.schemes import (
    StreamEnd,
    StreamTextDelta,
    StreamToolCallReady,
    TokenUsage,
)
from ..context.context import ContextBuilder
from ..memorys.manager import register_memory
from ..bus.types import OutboundMessageType
from ..schemes import RuntimeContext
from app.infrastructure.llms.utils import call_with_llm_fallback, is_llm_error_content
from ..tools.schemes import ToolCallItem, ToolResult


_LLM_ABORT_POLL_SEC = 0.2


class ReActAgent(BaseAgent):
    """ReAct 执行类，属性仅在 __init__ 内通过 self 赋值。"""

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
        super().__init__(
            user_id=user_id,
            session_id=session_id,
            channel_type=channel_type,
            channel_id=channel_id,
            agent_type=agent_type,
            workspace_path=workspace_path,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            next_step_prompt=next_step_prompt,
            llm_provider=llm_provider,
            llm_model=llm_model,
            **kwargs,
        )

        # 初始化子Agent上下文
        self._init_subagent_context()

        # 工具信息
        self.tool_choices = ToolChoice.AUTO
        self.special_tool_names: List[str] = ["ask_question", "terminate"]
        self._available_tools = None
        self._mcp_bridge = None
        self._init_tools_factory()

    # ------------------------------------------------------------------
    # Reset相关操作
    # ------------------------------------------------------------------
    def reset(self):
        '''
        Reset the agent
        '''
        super().reset()
        if self.subagent_manager:
            self.subagent_manager.cancel_tasks()
        self._mcp_bridge = None

    # ------------------------------------------------------------------
    # Abort相关操作
    # ------------------------------------------------------------------
    def request_abort(self, reason: AbortReason, message: Optional[str] = None) -> None:
        super().request_abort(reason, message)
        if self.subagent_manager:
            self.subagent_manager.cancel_tasks()

    def _init_subagent_context(self) -> None:
        '''
        Initialize sub agent context
        '''
        from .subagent import SubAgentManager
        self.subagent_manager = SubAgentManager(
            user_id=self.user_id,
            session_id=self.session_id,
            channel_type=self.channel_type,
            channel_id=self.channel_id,
            parent_agent_type=self.agent_type,
            workspace_path=str(self.workspace_path),
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            **self.params,
        )
        self._agent_context.subagent_manager = self.subagent_manager

    def _init_tools_factory(self) -> None:
        """根据 agent_config.tools（permissions / toolset / mode）解析并注册工具。"""
        try:
            if not self.agent_config:
                raise ValueError("Agent tools configuration is required")
            usable_tool_names = ToolPolicyResolver.resolve_agent_tools(self.agent_config)

            # 如果配置允许管理skill，则需要加上skill管理工具
            if self.skills_manager:
                if not self.skills_manager.allow_manage:
                    usable_tool_names = [n for n in usable_tool_names if n != "skill_manage"]
                elif "skill_manage" not in usable_tool_names:
                    usable_tool_names = sorted({*usable_tool_names, "skill_manage"})

            self._available_tools = ToolsFactory.from_permissions(
                allowed_names=usable_tool_names,
                ctx=self._agent_context,
            )
            # 为SubAgent绑定主Agent的工具
            self.subagent_manager.bind_parent_tools(
                self._available_tools.list_tool_names(),
                self.agent_config,
            )
        except Exception as e:
            logging.error(f"Error in agent tools registration: {str(e)}")
            raise e

    async def _connect_mcp_tools(self) -> None:
        """从 agent_config.mcp_servers 加载 MCP 并注册工具，返回本轮 run 的 bridge。"""
        ms = self.agent_config.get("mcp_servers")
        servers = list(ms) if isinstance(ms, list) else []
        if not servers:
            return
        try:
            from ..mcp.connector import MCPServerConnector
            self._mcp_bridge = await MCPServerConnector.connect_and_register(
                servers,
                self._available_tools,
            )
        except Exception as e:
            logging.error("Failed to connect MCP servers (will retry next run): %s", e)

    async def _build_prompt_and_question(self, question: str) ->str:
        '''
        构建系统提示词、用户提示词、下一步提示词、和用户问题

        Args:
            question: Input question
        Returns:
            question: str
        '''
        context_builder = ContextBuilder(
            ctx=self._agent_context,
            skills_manager=self.skills_manager,
            memory_manager=self._memory_manager,
        )
        self.system_prompt = await context_builder.build_system_prompt() or self.system_prompt
        new_question = await context_builder.build_user_content(question)
        return new_question

    async def _create_run_context(self) ->RuntimeContext:
        '''
        Create run context
        '''
        return RuntimeContext(
                last_llm=self._last_llm,
                actor_id=f"main:{self.session_id}" if self.session_id else "main:unknown",
                abort_controller=self._abort_controller,
                notify_user_callback=self.notify_user,
                mcp_bridge=self._mcp_bridge,
            )

    async def _refresh_mcp_lease(self) -> None:
        """已建连的 MCP 在 run 期间 pin；lazy 首次建连后补 pin。"""
        if self._mcp_bridge:
            await self._mcp_bridge.pin_and_touch_connected()

    async def run(self, question: str, *, is_internal: bool = False) -> str:
        """Run the agent
        
        Args:
            question: Input question
            
        Returns:
            str: Execution result
        """
        if not self.session_id:
            raise ValueError("Session ID is required")
        
        # 检查并重置状态
        if self._state != AgentState.IDLE:
            logging.warning(f"Agent is busy with state {self._state}, resetting...")
            self.reset()
        
        # 设置运行状态
        self._state = AgentState.RUNNING
        self._stream_open = False

        try:
            # 连接并注册 MCP 工具
            self._memory_manager = register_memory(memory_type="default", ctx=self._agent_context)
            self._mcp_bridge = await self._connect_mcp_tools()
            run_ctx = await self._create_run_context()

            # 构建提示词
            original_question = question
            question = await self._build_prompt_and_question(question)

            # 设置添加用户消息到history标志
            content = ""
            had_push_user_message = False
            context_overflow_recovered = False
            goal_reached = False
            # ReAct 主循环：任一步 is_aborted() 为真则不再调度新一轮 think_and_act
            while self._current_step < self._max_steps and self._state != AgentState.FINISHED and not self.is_aborted():
                self._current_step += 1
                await self._refresh_mcp_lease()

                content, tool_calls, usage, tool_pairs = await self.think_and_act(question, run_ctx)
                # 如果用户消息未推送，则推送
                if not had_push_user_message:
                    await self.push_history_message(Message.system_message(original_question) if is_internal else Message.user_message(original_question))
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
                        if is_llm_error_content(content):
                            raise RuntimeError(content.strip())
                        await self.push_history_message(Message.assistant_message(content))
                        if self.agent_mode == AgentMode.GOAL and goal_reached:
                            question = "你已完成循环操作，请回头再看看你是否达到了目标。"
                            goal_reached = True
                            continue
                        else:
                            break
                
                # 如果异终止，不需要后面上下文判断与压缩
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
                notice = f"Run aborted: {self._abort_reason_label()}."
                await self.push_history_message_and_notify_user(Message.assistant_message(notice))
                return notice
            return content
        except asyncio.CancelledError:
            if not self.is_aborted():
                self.request_abort(AbortReason.TASK_CANCELLED)
            notice = f"Run aborted: {self._abort_reason_label()}."
            await self.push_history_message_and_notify_user(Message.assistant_message(notice))
            return notice
        except Exception as e:
            # 异常也标记 RUNTIME_ERROR，便于日志与后续 Phase 1 长工具协作退出
            self.request_abort(AbortReason.RUNTIME_ERROR, str(e))
            self._state = AgentState.ERROR
            await self.push_history_message_and_notify_user(Message.assistant_message(f"Error in agent execution: {str(e)}"))
            raise
        finally:
            if self._mcp_bridge:
                await self._mcp_bridge.unpin_all()
            if self._stream_open:
                await self.notify_user(outbound_type=OutboundMessageType.STREAM_END)
            await self.notify_user(outbound_type=OutboundMessageType.RUN_END)
            if self.subagent_manager:
                self.subagent_manager.cancel_tasks()
            self.reset()
            # 记忆提取放到后台异步任务，不阻塞主流程
            if self._memory_manager is not None:
                await self.consolidate_memory()

    async def think_and_act(
        self,
        question: str,
        run_ctx: RuntimeContext,
    ) -> Tuple[str, List[ToolCall], TokenUsage, Optional[List[Tuple[ToolCall, ToolResult]]]]:
        """思考：无工具走 think_only，有工具走 think_with_act。"""
        try:
            if self.tool_choices == ToolChoice.NONE:
                content, usage = await self.think_only(question)
                return content, [], usage, None
            else:
                content, tool_calls, usage, tool_pairs = await self.think_with_act(question, run_ctx)
                return content, tool_calls, usage, tool_pairs
        except Exception as e:
            logging.error("Error in agent(%s) thinking process: %s", self.agent_type, e)
            raise RuntimeError(str(e)) from e

    async def think_only(
        self,
        question: str,
    ) -> Tuple[str, TokenUsage]:
        """无工具：仅 chat_stream，返回 (content, usage)。"""
        result, llm = await call_with_llm_fallback(
            self.llms_list,
            lambda llm: self._think_only_impl(llm, question),
        )
        self._last_llm = llm
        return result

    async def _think_only_impl(
        self,
        llm: Any,
        question: str,
    ) -> Tuple[str, TokenUsage]:
        history = await self.get_history_context()
        llm_task = asyncio.create_task(
            llm.chat_stream(
                system_prompt=self.system_prompt,
                user_prompt=self.user_prompt,
                user_question=question,
                history=history,
            )
        )
        try:
            while not llm_task.done():
                if self.is_aborted():
                    llm_task.cancel()
                    try:
                        await llm_task
                    except asyncio.CancelledError:
                        pass
                    return "", TokenUsage()
                await asyncio.sleep(_LLM_ABORT_POLL_SEC)
            stream, usage = llm_task.result()
        except asyncio.CancelledError:
            return "", TokenUsage()

        chunks: List[str] = []
        try:
            async for chunk in stream:
                if self.is_aborted():
                    break
                if isinstance(chunk, str) and chunk:
                    chunks.append(chunk)
                    await self.notify_user(content=chunk, outbound_type=OutboundMessageType.STREAM_DELTA)
        except asyncio.CancelledError:
            return "", TokenUsage()
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        if self.is_aborted():
            return "", TokenUsage()
        return "".join(chunks), usage

    async def think_with_act(
        self,
        question: str,
        run_ctx: RuntimeContext,
    ) -> Tuple[str, List[ToolCall], TokenUsage, List[Tuple[ToolCall, ToolResult]]]:
        """有工具：流式 LLM，参数闭合即调度执行，返回 (content, tool_calls, usage, tool_pairs)。"""
        result, llm = await call_with_llm_fallback(
            self.llms_list,
            lambda llm: self._think_with_act_impl(llm, question, run_ctx),
        )
        self._last_llm = llm
        return result

    async def _think_with_act_impl(
        self,
        llm: Any,
        question: str,
        run_ctx: RuntimeContext,
    ) -> Tuple[str, List[ToolCall], TokenUsage, List[Tuple[ToolCall, ToolResult]]]:
        history = await self.get_history_context()
        llm_task = asyncio.create_task(
            llm.ask_tools_stream(
                system_prompt=self.system_prompt,
                user_prompt=self.user_prompt,
                user_question=question,
                history=history,
                tools=self._available_tools.to_params(),
                tool_choice=self.tool_choices.value,
            )
        )

        # 工具结果回调函数
        results_by_id: Dict[str, ToolResult] = {}
        async def on_tool_run_result(item: ToolCallItem, result: ToolResult) -> None:
            results_by_id[item.tool_call_id] = result
            await self.notify_user(
                Message.tool_result_message(
                    f"{result.result}",
                    item.tool_name,
                    item.tool_call_id,
                    metadata=getattr(result, "metadata", None),
                )
            )

        # 创建工具调度器
        tool_scheduler = ToolScheduleSession(
            self._available_tools,
            ToolRunNotifier(on_tool_run_result=on_tool_run_result),
        )
        
        # 工具调度器取消回调函数
        def discard_schedule() -> None:
            if tool_scheduler is not None:
                tool_scheduler.discard_tasks()

        try:
            while not llm_task.done():
                if self.is_aborted():
                    llm_task.cancel()
                    discard_schedule()
                    try:
                        await llm_task
                    except asyncio.CancelledError:
                        pass
                    return "", [], TokenUsage(), []
                await asyncio.sleep(_LLM_ABORT_POLL_SEC)
            event_stream, usage = llm_task.result()
        except asyncio.CancelledError:
            discard_schedule()
            return "", [], TokenUsage(), []

        # 消费模型流式返回结果
        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        try:
            async for event in event_stream:
                if self.is_aborted():
                    discard_schedule()
                    break
                if isinstance(event, StreamTextDelta):
                    text_parts.append(event.text)
                    await self.notify_user(content=event.text, outbound_type=OutboundMessageType.STREAM_DELTA)
                elif isinstance(event, StreamToolCallReady):
                    # 创建工具调用
                    tool_call = ToolCall(
                        id=event.id,
                        function=Function(
                            name=event.name,
                            arguments=dict(event.arguments or {}),
                        ),
                    )
                    tool_calls.append(tool_call)
                    # 提交工具调用到工具调度器                    
                    tool_scheduler.submit(run_ctx, ToolCallItem.from_tool_call(tool_call))
                    await self.notify_user(
                        Message.tool_call_message(f"\n\n正在执行 {event.name}: {event.arguments or {}} ..."), 
                        outbound_type=OutboundMessageType.STREAM_DELTA
                    )
                elif isinstance(event, StreamEnd) and isinstance(event.usage, TokenUsage):
                    usage = event.usage
        except asyncio.CancelledError:
            discard_schedule()
            return "", [], TokenUsage(), []
        finally:
            close = getattr(event_stream, "aclose", None)
            if close is not None:
                await close()

        if self.is_aborted():
            discard_schedule()
            return "", [], TokenUsage(), []

        # 如果工具调用为空，则抛出异常
        if self.tool_choices == ToolChoice.REQUIRED and not tool_calls:
            raise ValueError("Tool calls required but none provided")

        # 等待工具调度器完成
        await tool_scheduler.wait_complete(run_ctx)
        # 获取工具调用和结果
        tool_pairs: List[Tuple[ToolCall, ToolResult]] = []
        for tc in tool_calls:
            result = results_by_id.get(tc.id)
            if result is None:
                logging.warning("tool call %s missing result after schedule, skipped", tc.id)
                continue
            tool_pairs.append((tc, result))
        return "".join(text_parts), tool_calls, usage, tool_pairs

    def _has_special_tools(self, tool_calls: List[ToolCall]) -> List[ToolCall]:
        return [
            toolcall
            for toolcall in tool_calls
            if toolcall.function.name in self.special_tool_names
        ]

    async def _handle_special_tool(self, special_tool_calls: List[ToolCall]) -> None:
        """特殊工具本轮执行完毕后的状态处理（可扩展）。"""
        self._state = AgentState.FINISHED
        names = [tc.function.name for tc in special_tool_calls]
        logging.info("Agent finished after special tool(s): %s", ", ".join(names))