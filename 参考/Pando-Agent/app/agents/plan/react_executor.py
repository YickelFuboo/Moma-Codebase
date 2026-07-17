"""Planning 节点 ReAct 执行器：调度 Harness 内置 Agent。"""
from ..core.react import ReActAgent
from ..schemes import AgentContext
from ..sessions.manager import SESSION_MANAGER
from .plan_graph import GraphNode, PlanGraphState

_PLAN_NODE_PARENT_KEY = "parent_session_id"
_PLAN_NODE_ID_KEY = "plan_node_id"
_PLAN_NODE_LABEL_KEY = "plan_node_label"


class ReactNodeExecutor:
    """Planning 图节点的 ReAct 执行（Harness 子 Agent）。"""

    @staticmethod
    async def run(
        plan_graph: PlanGraphState,
        graph_node: GraphNode,
        task: str,
        agent_ctx: AgentContext,
        agent_type: str,
    ) -> str:
        """在节点子 session 上运行 ReActAgent。"""
        react_session_id = await ReactNodeExecutor._ensure_node_session(
            plan_graph, graph_node, agent_ctx
        )
        react_agent = ReActAgent(
            user_id=agent_ctx.user_id,
            session_id=react_session_id,
            channel_type=agent_ctx.channel_type,
            channel_id=agent_ctx.channel_id,
            agent_type=agent_type,
            llm_provider=agent_ctx.llm_provider,
            llm_model=agent_ctx.llm_model,
            workspace_path=agent_ctx.workspace_path,
            **agent_ctx.params,
        )
        return (await react_agent.run(task, is_internal=True) or "").strip()

    @staticmethod
    async def _ensure_node_session(
        plan_graph: PlanGraphState,
        graph_node: GraphNode,
        agent_ctx: AgentContext,
    ) -> str:
        """为 ReAct 编排节点获取或创建 Harness 子 session，并写入 node_session_id。"""
        existing = plan_graph.node_session_id.get(graph_node.id)
        if existing:
            session = await SESSION_MANAGER.get_session(existing)
            if session:
                return existing
        node_session_id = await SESSION_MANAGER.create_session(
            user_id=agent_ctx.user_id,
            agent_type=graph_node.executor.agent_type,
            channel_type=agent_ctx.channel_type,
            description=f"[Planning] {graph_node.label or graph_node.id}",
            workspace_path=agent_ctx.workspace_path or None,
            metadata={
                _PLAN_NODE_PARENT_KEY: agent_ctx.session_id,
                _PLAN_NODE_ID_KEY: graph_node.id,
                _PLAN_NODE_LABEL_KEY: graph_node.label or graph_node.id,
            },
            llm_provider=agent_ctx.llm_provider,
            llm_model=agent_ctx.llm_model,
            is_internal=True,
        )
        plan_graph.node_session_id[graph_node.id] = node_session_id
        return node_session_id
