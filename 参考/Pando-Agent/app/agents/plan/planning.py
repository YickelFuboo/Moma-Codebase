"""Planning Agent：编排协调者（建图 + LangGraph 执行 + 会话编排）。"""
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from ..bus.queues import MESSAGE_GATEWAY
from ..bus.types import OutboundMessage, OutboundMessageType
from ..contants import (
    AGENT_CONFIG_DIR,
    AGENT_CONFIG_FILE,
    AGENT_CONTEXT_PATH,
    AGENT_TYPE_PLANNING,
    PLANNING_PROMPT_JUDGE_USER,
    PLANNING_PROMPT_USER,
)
from ..context.context import ContextBuilder
from ..core.base import AgentState, BaseAgent
from ..core.run_abort import AbortReason
from .langraph_excutor import (
    JudgeRouteCallback,
    LangGraphExecutor,
    PersistPlanGraphCallback,
)
from .plan_graph import (
    PLAN_GRAPH_METADATA_KEY,
    DirectExecGraph,
    EdgeCondition,
    GraphNode,
    PlanGraphPhase,
    PlanGraphState,
)
from ..schemes import RuntimeContext
from ..sessions.manager import SESSION_MANAGER
from ..sessions.message import Message
from app.infrastructure.llms.utils import call_with_llm_fallback, is_llm_response_failed
from app.infrastructure.llms.prompts.prompt_template_load import get_prompt_template
from ..tools.utils import extract_json_object


PLAN_MAX_GRAPH_NODES = 12
_LLM_ABORT_POLL_SEC = 0.2
_PARTIAL_START_RE = re.compile(
    r"(?:从(?:节点)?|start(?:\s+from(?:\s+node)?)?\s+)"
    r"[`'\"]?([A-Za-z][A-Za-z0-9_-]*)[`'\"]?"
    r"(?:\s*开始)?(?:\s*执行)?",
    re.IGNORECASE,
)


def parse_partial_start_node_id(
    question: str,
    graph: DirectExecGraph,
) -> Tuple[Optional[str], bool, Optional[str]]:
    """
    解析部分重跑起点。
    返回 (start_node_id, matched, token)：
    - matched=False：全量从 entry 执行，token 为 None
    - matched=True 且 start_node_id 有值：解析成功
    - matched=True 且 start_node_id 为 None：用户指定了节点但未找到，token 为原始输入
    """
    text = (question or "").strip()
    if not text:
        return None, False, None
    match = _PARTIAL_START_RE.search(text)
    if not match:
        return None, False, None
    token = (match.group(1) or "").strip()
    if not token:
        return None, True, None
    return graph.resolve_node_id(token), True, token


def _prose_without_json_blob(text: str) -> str:
    """去掉回复中的 JSON 代码块或最外层对象，保留模型文字说明。"""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE)
    if fence:
        return (stripped[: fence.start()] + stripped[fence.end() :]).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return (stripped[:start] + stripped[end + 1 :]).strip()
    return stripped


def parse_planning_llm_response(raw: str) -> Tuple[str, Optional[DirectExecGraph]]:
    """
    从建图 LLM 全文解析 (文字说明, 执行图)。
    说明为 JSON 外的叙述；图为 extract_json_object + DirectExecGraph 校验后的结果。
    """
    text = (raw or "").strip()
    if not text:
        return "", None
    parsed = extract_json_object(text)
    if not parsed:
        return text, None
    graph = DirectExecGraph.from_dict(parsed)
    if graph is None:
        return text, None
    return _prose_without_json_blob(text), graph


class PlanningAgent(BaseAgent):
    """编排协调者：建图 → LangGraph 调度专业 Agent → 结果返回用户。"""

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
        temperature: Optional[float] = None,
        memory_window: Optional[int] = None,
        max_steps: Optional[int] = None,
        max_duplicate_steps: Optional[int] = None,
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
            temperature=temperature,
            memory_window=memory_window,
            max_steps=max_steps,
            max_duplicate_steps=max_duplicate_steps,
            **kwargs,
        )

        # 是否重新生成Graph
        self.is_recreate_graph = False

    async def _load_plan_graph(self) -> PlanGraphState:
        session = await SESSION_MANAGER.get_session(self.session_id)
        if not session:
            return PlanGraphState()
        return PlanGraphState.from_metadata(session.metadata) or PlanGraphState()

    async def _save_plan_graph(self, state: PlanGraphState) -> None:
        session = await SESSION_MANAGER.get_session(self.session_id)
        if not session:
            return
        session.metadata[PLAN_GRAPH_METADATA_KEY] = state.to_metadata()
        await SESSION_MANAGER.save_session(session)

    async def _release_stuck_plan_execution(self) -> None:
        """执行中断或异常时，避免 metadata.phase 长期停留在 executing。"""
        plan_state = await self._load_plan_graph()
        if plan_state.phase != PlanGraphPhase.EXECUTING:
            return
        plan_state.phase = PlanGraphPhase.IDLE
        plan_state.running_node_ids = []
        await self._save_plan_graph(plan_state)

    async def _reply_user(self, text: str) -> str:
        """写入 Planning 主会话历史并推送给前端。"""
        content = (text or "").strip()
        if content:
            await self.push_history_message_and_notify_user(Message.assistant_message(content))
        return content

    async def run(self, question: str, *, is_internal: bool = False) -> str:
        if not self.session_id:
            raise ValueError("Session ID is required")

        if self._state != AgentState.IDLE:
            logging.warning("PlanningAgent busy, resetting state=%s", self._state)
            self.reset()
        
        # 设置运行状态
        self._state = AgentState.RUNNING
        self._stream_open = False

        context_builder = ContextBuilder(
            ctx=self._agent_context,
            skills_manager=self.skills_manager,
        )
        try:
            # 更新参数，构造Prompt需要使用
            self._agent_context.params.update(self.params)
            self._agent_context.params.update({
                "user_goal": question,
                "agent_catalog": self.list_agent_catalog() or "(暂无可用 Agent)",
                "plan_max_graph_nodes": PLAN_MAX_GRAPH_NODES,
            })
            # 构建提示词
            self.system_prompt = await context_builder.build_system_prompt() or self.system_prompt
            run_ctx = RuntimeContext(
                actor_id=f"planning:{self.session_id}" if self.session_id else "planning:unknown",
                abort_controller=self._abort_controller,
                notify_user_callback=self.notify_user,
                push_history_callback=self.push_history_message,
                params=self._agent_context.params_dict(),
            )

            plan_content: Optional[str] = None
            if self.is_recreate_graph:
                plan_state = await self._load_plan_graph()
                # 清空历史，重新执行
                plan_state.clear_history()
            else:
                plan_state = await self._load_plan_graph()

            plan_state.user_goal = question
            # 首次只创建图谱图，然后用户确认后开始执行
            if not plan_state.resolve_graph():
                plan_content, exec_graph = await self._planning(plan_state)
                if exec_graph is None:
                    return await self._reply_user("编排方案生成失败，请重试。")
                plan_state.plan_graph = exec_graph
                plan_state.phase = PlanGraphPhase.IDLE
                plan_state.running_node_ids = []
                await self._save_plan_graph(plan_state)

                # 推送用户消息
                await self.push_history_message(Message.user_message(question))
                if plan_content:
                    await self.push_history_message(Message.assistant_message(plan_content))
                await self._reply_user(
                    "已制定编排方案，请查看拓扑图确认编排方案。"
                    "确认后请发送「开始执行」；若需从中间步骤重跑，可发送「从 <节点ID> 开始执行」。"
                    f"\n\n{exec_graph.format_summary()}"
                )
                # 首次创建Graph不做执行，用户输入执行后才启动执行
                return plan_content or "编排方案已就绪，请确认后执行。"

            exec_graph = plan_state.resolve_graph()
            if exec_graph is None:
                return await self._reply_user("编排方案无效或缺失，无法执行。")

            # 解析用户指定的启动执行节点
            partial_start, partial_matched, partial_token = parse_partial_start_node_id(question, exec_graph)
            start_node_id: Optional[str] = None
            if partial_matched:
                if not partial_start:
                    bad_token = (partial_token or "").strip() or "?"
                    return await self._reply_user(
                        f"未找到节点「{bad_token}」，请使用节点 ID（如 step_b）或步骤名称。"
                    )
                if exec_graph.is_entry_node(partial_start):
                    # 起始节点等同于全量执行：清空全部执行记录，从 entry 跑完整流程
                    plan_state.clear_history(clear_session_id=False)
                else:
                    start_node_id = partial_start
                    plan_state.clear_execution_from_node(partial_start)
            else:
                plan_state.clear_history(clear_session_id=False)

            if self._stream_open:
                await self.notify_user(outbound_type=OutboundMessageType.STREAM_END)

            await self.push_history_message(Message.user_message(question))

            plan_state.phase = PlanGraphPhase.EXECUTING
            plan_state.running_node_ids = []
            await self._save_plan_graph(plan_state)
            if start_node_id:
                node_label = exec_graph.nodes[start_node_id].label or start_node_id
                await self._reply_user(
                    f"从步骤「{node_label}」开始执行：\n\n{exec_graph.format_summary()}"
                )
            else:
                await self._reply_user(f"已制定编排方案，开始执行：\n\n{exec_graph.format_summary()}")
            body = await LangGraphExecutor.run(
                plan_state,
                self._agent_context,
                run_ctx,
                persist_plangraph_callback=self._persist_planning_graph,
                judge_route_callback=self._judge_callback,
                start_node_id=start_node_id,
            )
            return plan_content or f"编排完成。\n\n{body}"

        except asyncio.CancelledError:
            if not self.is_aborted():
                self.request_abort(AbortReason.TASK_CANCELLED)
            await self._release_stuck_plan_execution()
            return await self._reply_user(f"已中止：{self._abort_reason_label()}")
        except Exception as e:
            self.request_abort(AbortReason.RUNTIME_ERROR, str(e))
            self._state = AgentState.ERROR
            await self._release_stuck_plan_execution()
            await self._reply_user(f"编排失败：{e}")
            raise
        finally:
            if self._stream_open:
                await self.notify_user(outbound_type=OutboundMessageType.STREAM_END)
            await self.notify_user(outbound_type=OutboundMessageType.RUN_END)
            self.reset()

    async def _planning(
        self, state: PlanGraphState
    ) -> Tuple[str, Optional[DirectExecGraph]]:
        """生成执行图；返回 (用于会话展示的摘要文本, 图对象)。"""
        result, llm = await call_with_llm_fallback(
            self.llms_list,
            self._planning_with_llm,
        )
        self._last_llm = llm
        return result

    async def _planning_with_llm(
        self, llm: Any
    ) -> Tuple[str, Optional[DirectExecGraph]]:
        if not self.system_prompt.strip():
            logging.error("Planning system prompt missing: %s/prompts", self.agent_path)
            return "", None

        history = await self.get_history_context()
        prompt_dir = str(Path(self.agent_path) / AGENT_CONTEXT_PATH)
        user = get_prompt_template(prompt_dir, PLANNING_PROMPT_USER, self._agent_context.params_dict()).strip()
        llm_task = asyncio.create_task(
            llm.chat_stream(
                system_prompt=self.system_prompt,
                user_prompt="",
                user_question=user,
                history=history,
                temperature=0.2,
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
                    return "", None
                await asyncio.sleep(_LLM_ABORT_POLL_SEC)
            stream, _usage = llm_task.result()
        except asyncio.CancelledError:
            return "", None

        chunks: List[str] = []
        try:
            async for chunk in stream:
                if self.is_aborted():
                    break
                if isinstance(chunk, str) and chunk:
                    chunks.append(chunk)
                    await self.notify_user(content=chunk, outbound_type=OutboundMessageType.STREAM_DELTA)
        except asyncio.CancelledError:
            return "", None
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        
        # 如果被中止，返回空
        if self.is_aborted():
            return "", None

        raw = "".join(chunks)
        explanation, exec_graph = parse_planning_llm_response(raw)
        if exec_graph is None:
            return "", None
        plan_text = explanation.strip() or exec_graph.format_summary()
        return plan_text, exec_graph

    async def _persist_planning_graph(self, graph: PlanGraphState, summary: str) -> None:
        """落库编排快照；summary 非空时才写入主会话聊天（避免与步骤开始/结束通知重复）。"""
        await self._save_plan_graph(graph)
        text = (summary or "").strip()
        if text:
            await self.push_history_message_and_notify_user(Message.assistant_message(text))

    async def _judge_callback(
        self,
        graph_node: GraphNode,
        node_output: str,
        pre_outputs: Dict[str, str],
        user_goal: str,
    ) -> EdgeCondition:
        """审查节点路由：由 Planning 定义 prompt 与判定规则，执行器仅通过回调调用。"""
        result, llm = await call_with_llm_fallback(
            self.llms_list,
            lambda model: self._judge_route_with_llm(
                model, graph_node, node_output, pre_outputs, user_goal
            ),
        )
        self._last_llm = llm
        return result

    async def _judge_route_with_llm(
        self,
        llm: Any,
        graph_node: GraphNode,
        node_output: str,
        pre_outputs: Dict[str, str],
        user_goal: str,
    ) -> EdgeCondition:
        params = {
            "user_goal": user_goal,
            "pre_outputs_text": "\n\n".join(f"[{k}]\n{v}" for k, v in pre_outputs.items()) or "(无)",
            "reviewer_label": graph_node.label,
            "review_output": node_output,
        }
        prompt_dir = str(Path(self.agent_path) / AGENT_CONTEXT_PATH)
        user = get_prompt_template(prompt_dir, PLANNING_PROMPT_JUDGE_USER, params).strip()
        llm_task = asyncio.create_task(
            llm.chat(
                system_prompt=self.system_prompt,
                user_prompt="",
                user_question=user,
                history=[],
                temperature=0.1,
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
                    return EdgeCondition.REJECT
                await asyncio.sleep(_LLM_ABORT_POLL_SEC)
            resp, _usage = llm_task.result()
        except asyncio.CancelledError:
            return EdgeCondition.REJECT
        if is_llm_response_failed(resp):
            detail = (getattr(resp, "content", None) or str(resp) or "审查 LLM 调用失败").strip()
            raise RuntimeError(f"审查步骤「{graph_node.label}」路由判定失败：{detail}")
        text = (resp.content if hasattr(resp, "content") else str(resp) or "").strip().lower()
        if "reject" in text or any(k in text for k in ("不通过", "驳回", "返工", "未通过")):
            return EdgeCondition.REJECT
        return EdgeCondition.PASS

    @staticmethod
    def list_agent_catalog() -> str:
        lines: List[str] = []
        if not AGENT_CONFIG_DIR.is_dir():
            return ""
        for p in sorted(AGENT_CONFIG_DIR.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            if p.name.lower() == AGENT_TYPE_PLANNING.lower():
                continue
            cfg_path = p / AGENT_CONFIG_FILE
            name_zh = p.name
            desc_zh = ""
            if cfg_path.is_file():
                try:
                    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        name_zh = raw.get("name_zh") or p.name
                        desc_zh = raw.get("description_zh") or ""
                except Exception:
                    pass
            lines.append(f"- {p.name}: {name_zh} — {desc_zh}")
        return "\n".join(lines)