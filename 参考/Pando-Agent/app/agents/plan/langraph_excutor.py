import asyncio
import operator
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from .plan_graph import (
    DirectExecGraph,
    END_NODE,
    EdgeCondition,
    GraphEdge,
    GraphNode,
    PlanGraphPhase,
    PlanGraphState,
)
from app.infrastructure.llms.utils import ensure_not_llm_error_content
from ..schemes import AgentContext, RuntimeContext
from ..sessions.message import Message
from app.config.settings import settings
from .react_executor import ReactNodeExecutor


PersistPlanGraphCallback = Callable[[PlanGraphState, str], Awaitable[None]]
JudgeRouteCallback = Callable[
    [GraphNode, str, Dict[str, str], str],
    Awaitable[EdgeCondition],
]

_CHECKPOINTER: Optional[AsyncSqliteSaver] = None
_CHECKPOINTER_CONN: Optional[aiosqlite.Connection] = None
_CHECKPOINTER_LOCK = asyncio.Lock()
_PLAN_RUNNING_LOCK = asyncio.Lock()


def _merge_str_dict(left: Optional[Dict[str, str]], right: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def _merge_int_dict(left: Optional[Dict[str, int]], right: Optional[Dict[str, int]]) -> Dict[str, int]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def _sync_plan_running(plan_graph: PlanGraphState, running_ids: List[str]) -> None:
    plan_graph.running_node_ids = list(running_ids)


async def _get_checkpointer() -> AsyncSqliteSaver:
    global _CHECKPOINTER, _CHECKPOINTER_CONN
    async with _CHECKPOINTER_LOCK:
        if _CHECKPOINTER is None:
            db_path = Path(settings.runtime_data_dir) / "planning_checkpoints.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _CHECKPOINTER_CONN = await aiosqlite.connect(str(db_path))
            _CHECKPOINTER = AsyncSqliteSaver(_CHECKPOINTER_CONN)
        return _CHECKPOINTER


def _lg_dest(to_id: str) -> str:
    """JSON 图中的 END_NODE → LangGraph END，否则为业务节点 id。"""
    return END if to_id == END_NODE else to_id


def _execution_thread_id(session_id: str, start: str, *, partial: bool) -> str:
    """每次编排执行使用独立 thread_id，避免 checkpoint 中 node_iterations 等状态跨轮次残留。"""
    sid = (session_id or "unknown").strip() or "unknown"
    run_token = uuid.uuid4().hex[:12]
    if partial:
        return f"{sid}:from:{start}:{run_token}"
    return f"{sid}:run:{run_token}"


class LangGraphRunState(TypedDict, total=False):
    """单次 LangGraph invoke 在节点间传递的状态。"""
    user_goal: str
    node_outputs: Annotated[Dict[str, str], _merge_str_dict]  # 节点产出，key: 节点 id，value: 产出
    pre_node_reject_infos: Annotated[Dict[str, str], _merge_str_dict]  # key=返工节点 id，value=reject 源节点驳回说明
    node_iterations: Annotated[Dict[str, int], _merge_int_dict]  # 节点重试次数，key: 节点 id，value: 重试次数
    last_route: str  # 上次路由条件（pass / reject / always）
    summary_parts: Annotated[List[str], operator.add]  # 总结片段
    aborted: bool  # 是否中止
    error_message: str  # 错误信息


class LangGraphExecutor:

    @staticmethod
    def _resolve_start_node(graph: DirectExecGraph, start_node_id: Optional[str]) -> str:
        """确定本次 LangGraph 的入口节点 id。

        start_node_id 为空时使用图的 entry；否则使用指定节点（部分重跑）。
        节点不存在时抛出 ValueError。
        """
        start = (start_node_id or graph.entry_node_id or "").strip()
        if not start or start not in graph.nodes:
            raise ValueError(f"起始节点不存在: {start or '(空)'}")
        return start

    @staticmethod
    def _validate_partial_start(plan_graph: PlanGraphState, graph: DirectExecGraph, start: str) -> Optional[str]:
        """校验部分重跑的前置条件：所有上游步骤必须已有 node_outputs。

        从 entry 开始时无需校验，返回 None。
        校验通过返回 None；缺上游产出时返回给用户看的错误文案。
        """
        if start == graph.entry_node_id:
            return None
        missing = [
            nid for nid in sorted(graph.ancestors(start))
            if nid not in plan_graph.node_outputs
        ]
        if not missing:
            return None
        labels = [graph.nodes[nid].label or nid for nid in missing]
        node = graph.nodes[start]
        label = node.label or start
        return (
            f"无法从步骤「{label}」开始：上游步骤 {labels} 尚无产出，"
            "请先完整执行或发送「开始执行」。"
        )

    @staticmethod
    async def run(
        plan_graph: PlanGraphState,
        agent_ctx: AgentContext,
        runtime_ctx: RuntimeContext,
        persist_plangraph_callback: Optional[PersistPlanGraphCallback] = None,
        judge_route_callback: Optional[JudgeRouteCallback] = None,
        start_node_id: Optional[str] = None,
    ) -> str:
        if runtime_ctx.is_aborted():
            return "编排已中止"

        graph = plan_graph.resolve_graph()
        if graph is None:
            return "编排方案无效或缺失，无法执行。"

        try:
            start = LangGraphExecutor._resolve_start_node(graph, start_node_id)
        except ValueError as e:
            return str(e)

        partial = bool((start_node_id or "").strip()) and not graph.is_entry_node(start or "")
        if partial:
            err = LangGraphExecutor._validate_partial_start(plan_graph, graph, start)
            if err:
                return err

        # 初始化运行状态
        initial: LangGraphRunState = {
            "user_goal": plan_graph.user_goal,
            "node_outputs": dict(plan_graph.node_outputs),
            "pre_node_reject_infos": dict(plan_graph.pre_node_reject_infos),
            "node_iterations": dict(plan_graph.node_iterations),
            "last_route": EdgeCondition.ALWAYS.value,
            "summary_parts": [],
            "aborted": False,
            "error_message": "",
        }

        plan_graph.phase = PlanGraphPhase.EXECUTING
        start_label = graph.nodes[start].label or start
        if persist_plangraph_callback is not None:
            if partial and start != graph.entry_node_id:
                await persist_plangraph_callback(
                    plan_graph,
                    f"从步骤「{start_label}」开始执行编排方案…",
                )
            else:
                await persist_plangraph_callback(plan_graph, "正在执行编排方案…")

        # 编译 LangGraph 工作流
        compiled = LangGraphExecutor._build_workflow(
            plan_graph,
            agent_ctx,
            runtime_ctx,
            persist_plangraph_callback,
            judge_route_callback,
            start_node_id=start,
        ).compile(checkpointer=await _get_checkpointer())

        thread_id = _execution_thread_id(agent_ctx.session_id or "", start, partial=partial)

        # 执行 LangGraph 工作流
        final_result = await compiled.ainvoke(
            initial,
            {"configurable": {"thread_id": thread_id}},
        )

        # 执行结果处理  
        if not isinstance(final_result, dict):
            return "(无执行结果)"
        plan_graph.node_outputs = dict(final_result.get("node_outputs") or {})
        plan_graph.pre_node_reject_infos = dict(final_result.get("pre_node_reject_infos") or {})
        plan_graph.node_iterations = dict(final_result.get("node_iterations") or {})
        plan_graph.running_node_ids = []
        if final_result.get("aborted"):
            plan_graph.phase = PlanGraphPhase.IDLE
        else:
            plan_graph.phase = PlanGraphPhase.DONE
        if persist_plangraph_callback is not None:
            done_msg = "编排已中止。" if final_result.get("aborted") else "编排执行完成。"
            await persist_plangraph_callback(plan_graph, done_msg)

        # 返回执行结果
        if final_result.get("error_message"):
            return str(final_result["error_message"])
        summary_parts = final_result.get("summary_parts") or []
        return "\n\n".join(summary_parts) if summary_parts else "(无执行结果)"

    @staticmethod
    def _build_workflow(
        plan_graph: PlanGraphState,
        agent_ctx: AgentContext,
        runtime_ctx: RuntimeContext,
        persist_plangraph_callback: Optional[PersistPlanGraphCallback],
        judge_route_callback: Optional[JudgeRouteCallback],
        start_node_id: Optional[str] = None,
    ) -> StateGraph:
        # 获取有向序列图
        graph = plan_graph.resolve_graph()
        if graph is None:
            raise ValueError("编排方案无效或缺失，无法执行。")

        entry = LangGraphExecutor._resolve_start_node(graph, start_node_id)
        def route_after(node_id: str):
            def _route(run_state: LangGraphRunState) -> Any:
                if run_state.get("aborted"):
                    return END
                try:
                    cond = EdgeCondition(run_state.get("last_route") or EdgeCondition.ALWAYS.value)
                except ValueError:
                    cond = EdgeCondition.ALWAYS
                next_ids = graph.resolve_next_node_ids(node_id, cond)
                if not next_ids:
                    return END
                dests = [_lg_dest(nid) for nid in next_ids]
                if len(dests) == 1:
                    return dests[0]
                return dests
            return _route

        # 构建 LangGraph 工作流
        workflow: StateGraph = StateGraph(LangGraphRunState)
        for graph_node in graph.nodes.values():
            workflow.add_node(
                graph_node.id,
                partial(
                    LangGraphExecutor._run_graph_node,
                    plan_graph=plan_graph,
                    graph_node=graph_node,
                    agent_ctx=agent_ctx,
                    runtime_ctx=runtime_ctx,
                    persist_plangraph_callback=persist_plangraph_callback,
                    judge_route_callback=judge_route_callback,
                ),
            )
        workflow.add_edge(START, entry)
        for node_id in graph.nodes:
            out_edges = graph.outgoing_edges(node_id)
            # 没有出边，直接作为终点
            if not out_edges:
                workflow.add_edge(node_id, END)
                continue

            # 出边有审查条件，要求当前节点往后向哪些节点执行需要注册业务自定义的route_after
            if graph.has_review_outgoing_edges(node_id):
                path_map = {END: END}
                for edge in out_edges:
                    dest = _lg_dest(edge.to_id)
                    path_map[dest] = dest
                workflow.add_conditional_edges(node_id, route_after(node_id), path_map)
            else:
                # 没有审查条件，直接向LangGraph注册无条件边
                for edge in out_edges:
                    workflow.add_edge(node_id, _lg_dest(edge.to_id))
        return workflow

    @staticmethod
    async def _run_graph_node(
        run_state: LangGraphRunState,
        plan_graph: PlanGraphState,
        graph_node: GraphNode,
        agent_ctx: AgentContext,
        runtime_ctx: RuntimeContext,
        persist_plangraph_callback: Optional[PersistPlanGraphCallback],
        judge_route_callback: Optional[JudgeRouteCallback],
    ) -> Dict[str, Any]:
        graph = plan_graph.resolve_graph()
        if graph is None:
            raise ValueError("编排方案无效或缺失，无法执行。")

        # 检查是否中止
        if runtime_ctx.is_aborted():
            return {"aborted": True, "error_message": "编排已中止"}

        current_node_id = graph_node.id         
        # 判断节点超过最大执行次数      
        iterations = dict(run_state.get("node_iterations") or {})
        node_iterations = iterations.get(current_node_id, 0) + 1
        if node_iterations > graph_node.max_iterations:
            plan_graph.node_iterations[current_node_id] = node_iterations
            async with _PLAN_RUNNING_LOCK:
                running_ids = list(plan_graph.running_node_ids or [])
                if current_node_id in running_ids:
                    running_ids.remove(current_node_id)
                _sync_plan_running(plan_graph, running_ids)
            msg = f"步骤「{graph_node.label}」超过最大重试 {graph_node.max_iterations} 次。"
            if persist_plangraph_callback is not None:
                await persist_plangraph_callback(plan_graph, f"{msg}编排已停止。")
            raise RuntimeError(msg)

        # 更新计划图状态
        plan_graph.node_iterations[current_node_id] = node_iterations
        async with _PLAN_RUNNING_LOCK:
            running_ids = list(plan_graph.running_node_ids or [])
            if current_node_id not in running_ids:
                running_ids.append(current_node_id)
            _sync_plan_running(plan_graph, running_ids)
            plan_graph.phase = PlanGraphPhase.EXECUTING
            executor_label = graph_node.executor.agent_type
            if persist_plangraph_callback is not None:
                await persist_plangraph_callback(
                    plan_graph,
                    f"正在执行步骤「{graph_node.label}」（{executor_label}）…",
                )

        # 运行Node
        node_outputs = dict(run_state.get("node_outputs") or {})
        pre_node_reject_infos = dict(run_state.get("pre_node_reject_infos") or {})
        pred_ids = graph.predecessor_ids(current_node_id)
        pre_outputs = (
            {pid: node_outputs[pid] for pid in pred_ids if pid in node_outputs}
            if pred_ids
            else {nid: out for nid, out in node_outputs.items() if nid != current_node_id}
        )
        try:
            output = await LangGraphExecutor.run_node(
                plan_graph,
                graph_node,
                run_state.get("user_goal") or "",
                agent_ctx,
                runtime_ctx,
                pre_outputs,
                pre_node_reject_infos.get(current_node_id, ""),
            )
            ensure_not_llm_error_content(output, context=f"步骤「{graph_node.label}」")

            last_route = EdgeCondition.ALWAYS.value
            if graph.has_review_outgoing_edges(current_node_id):
                if judge_route_callback is None:
                    raise ValueError(f"步骤「{graph_node.label}」需要审查路由，但未提供 judge_route_callback 回调")
                route = await judge_route_callback(
                    graph_node,
                    output,
                    pre_outputs,
                    run_state.get("user_goal") or "",
                )
                last_route = route.value
                if route == EdgeCondition.REJECT:
                    reject_msg = f"步骤「{graph_node.label}」驳回意见：\n{output}"
                    for edge in graph.outgoing_edges(current_node_id, EdgeCondition.REJECT):
                        reject_target_id = edge.to_id
                        if reject_target_id in graph.nodes:
                            pre_node_reject_infos[reject_target_id] = reject_msg

            async with _PLAN_RUNNING_LOCK:
                running_ids = list(plan_graph.running_node_ids or [])
                if current_node_id in running_ids:
                    running_ids.remove(current_node_id)
                _sync_plan_running(plan_graph, running_ids)
                plan_graph.node_outputs[current_node_id] = output
                plan_graph.node_iterations[current_node_id] = node_iterations
                plan_graph.pre_node_reject_infos = pre_node_reject_infos
                if persist_plangraph_callback is not None:
                    done_snippet = output[:500] + ("…" if len(output) > 500 else "")
                    await persist_plangraph_callback(
                        plan_graph,
                        f"步骤「{graph_node.label}」已完成。\n\n{done_snippet}",
                    )

            return {
                "node_outputs": {current_node_id: output},
                "node_iterations": {current_node_id: node_iterations},
                "pre_node_reject_infos": pre_node_reject_infos,
                "last_route": last_route,
                "summary_parts": [f"### {graph_node.label}\n{output[:2000]}"],
            }
        except Exception as exc:
            async with _PLAN_RUNNING_LOCK:
                running_ids = list(plan_graph.running_node_ids or [])
                if current_node_id in running_ids:
                    running_ids.remove(current_node_id)
                _sync_plan_running(plan_graph, running_ids)
            if persist_plangraph_callback is not None:
                await persist_plangraph_callback(
                    plan_graph,
                    f"步骤「{graph_node.label}」执行失败，编排已停止：{exc}",
                )
            raise

    @staticmethod
    def _build_react_task(
        graph_node: GraphNode,
        user_goal: str,
        pre_outputs: Dict[str, str],
        feedback: str = "",
    ) -> str:
        parts = [
            f"## 用户任务\n{user_goal}",
            f"## 当前步骤\n{graph_node.label} ({graph_node.id})",
            f"## 步骤说明\n{graph_node.task}",
        ]
        if pre_outputs:
            parts.append("## 前置步骤产出")
            for nid, out in pre_outputs.items():
                parts.append(f"### {nid}\n{out}")
        if feedback:
            parts.append(f"## 修订意见\n{feedback}")
        return "\n\n".join(parts)

    @staticmethod
    async def run_node(
        plan_graph: PlanGraphState,
        graph_node: GraphNode,
        user_goal: str,
        agent_ctx: AgentContext,
        runtime_ctx: RuntimeContext,
        pre_outputs: Dict[str, str],
        feedback: str = "",
    ) -> str:
        md_task = LangGraphExecutor._build_react_task(
            graph_node, user_goal, pre_outputs, feedback
        )
        agent_type = graph_node.executor.agent_type
        step_start = f"开始执行步骤「{graph_node.label}」（Agent: {agent_type}）"
        start_notice = f"{step_start}\n\n{md_task}"
        if runtime_ctx.push_history_callback:
            await runtime_ctx.push_history_callback(Message.assistant_message(start_notice))
        if runtime_ctx.notify_user_callback:
            await runtime_ctx.notify_user_callback(Message.assistant_message(start_notice))
        result = await ReactNodeExecutor.run(
            plan_graph,
            graph_node,
            md_task,
            agent_ctx,
            agent_type,
        )
        ensure_not_llm_error_content(result, context=f"步骤「{graph_node.label}」")
        step_stop = f"步骤「{graph_node.label}」（Agent: {agent_type}）执行完毕"
        stop_notice = f"{step_stop}\n\n{result}"
        if runtime_ctx.push_history_callback:
            await runtime_ctx.push_history_callback(Message.assistant_message(stop_notice))
        if runtime_ctx.notify_user_callback:
            await runtime_ctx.notify_user_callback(Message.assistant_message(stop_notice))
        return result