from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from .node_config import GraphNodeExecutor


#===============
# 有向序列图定义
#===============
START_NODE = "START"
END_NODE = "END"
_REVIEW_CONDITIONS = frozenset({"pass", "reject"})

@dataclass
class GraphNode:
    """图中的一个执行步骤；executor 描述 ReAct Agent 执行方案。"""
    id: str
    label: str = ""
    task: str = ""
    max_iterations: int = 3
    executor: GraphNodeExecutor = field(default_factory=GraphNodeExecutor.from_react)


class EdgeCondition(str, Enum):
    """边上的路由条件：always 为继续前进时的默认后继；pass/reject 为审查条件后继。"""
    ALWAYS = "always"
    PASS = "pass"   # 通过路由
    REJECT = "reject"   # 驳回路由


@dataclass
class GraphEdge:
    """from → to，condition 决定 LangGraph 条件路由时的匹配键。"""
    from_id: str
    to_id: str
    condition: EdgeCondition = EdgeCondition.ALWAYS


@dataclass
class DirectExecGraph:
    """有向执行图：节点 + 条件边 + entry；供校验与 LangGraph 构图。"""
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)
    entry_node_id: str = ""  # 入口节点id

    def is_valid(self) -> bool:
        if not self.entry_node_id or self.entry_node_id not in self.nodes:
            return False
        if not any(e.from_id == START_NODE for e in self.edges):
            return False
        if not any(e.to_id == END_NODE for e in self.edges):
            return False
        return True

    def outgoing_edges(self, node_id: str, condition: Optional[EdgeCondition] = None) -> List[GraphEdge]:
        """按 from_id 与 condition 过滤出边；无 condition 时返回所有出边。"""
        items = [e for e in self.edges if e.from_id == node_id]
        if condition is not None:
            items = [e for e in items if e.condition == condition]
        return items

    def predecessor_ids(self, node_id: str) -> List[str]:
        """直接前驱节点 id（不含 START/END），用于组装 pre_outputs。"""
        seen: set[str] = set()
        preds: List[str] = []
        for edge in self.edges:
            if edge.to_id != node_id or edge.from_id in (START_NODE, END_NODE):
                continue
            if edge.from_id in seen:
                continue
            seen.add(edge.from_id)
            preds.append(edge.from_id)
        return preds

    def resolve_next_node_ids(self, current_node_id: str, condition: EdgeCondition) -> List[str]:
        """
        解析路由后继（审查节点 judge 仅产出 pass / reject）：
        - pass：全部 pass 出边 + 全部 always 出边（继续前进，并行去重）
        - reject：仅 reject 出边（返工，不激活 always / pass）
        - always：仅 always 出边（无审查节点的 route_after 兜底）
        """
        if condition == EdgeCondition.REJECT:
            return [e.to_id for e in self.outgoing_edges(current_node_id, EdgeCondition.REJECT)]
        if condition == EdgeCondition.PASS:
            pass_ids = [e.to_id for e in self.outgoing_edges(current_node_id, EdgeCondition.PASS)]
            always_ids = [e.to_id for e in self.always_outgoing_edges(current_node_id)]
            seen: set[str] = set()
            result: List[str] = []
            for nid in pass_ids + always_ids:
                if nid in seen:
                    continue
                seen.add(nid)
                result.append(nid)
            return result
        return [e.to_id for e in self.always_outgoing_edges(current_node_id)]

    def has_review_outgoing_edges(self, node_id: str) -> bool:
        """该节点是否存在 pass/reject 出边（需 LLM 路由判定）。"""
        return any(e.condition.value in _REVIEW_CONDITIONS for e in self.outgoing_edges(node_id))

    def always_outgoing_edges(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.outgoing_edges(node_id) if e.condition == EdgeCondition.ALWAYS]

    def ancestors(self, node_id: str) -> set[str]:
        """沿入边反向遍历，返回必须在 node_id 之前的所有步骤 id（不含 START/END）。

        用途：部分重跑前检查上游是否已有 node_outputs；缺产出则不允许从该步开始。
        例：A → B → C 时 ancestors('C') == {'A', 'B'}。
        """
        result: set[str] = set()
        current_ids = {node_id}
        while current_ids:
            next_ids: set[str] = set()
            for nid in current_ids:
                for edge in self.edges:
                    if edge.to_id != nid or edge.from_id in (START_NODE, END_NODE):
                        continue
                    if edge.from_id not in result:
                        result.add(edge.from_id)
                        next_ids.add(edge.from_id)
            current_ids = next_ids
        return result

    def downstream(self, node_id: str) -> set[str]:
        """沿出边正向遍历，返回 node_id 之后还会经过的所有步骤 id（不含 END，不含自身）。

        用途：部分重跑时与起点一起清空 node_outputs / iterations，只保留起点之前的记录。
        例：A → B → C 时 downstream('A') == {'B', 'C'}；downstream('B') == {'C'}。
        """
        result: set[str] = set()
        current_ids = {node_id}
        while current_ids:
            next_ids: set[str] = set()
            for nid in current_ids:
                for edge in self.outgoing_edges(nid):
                    if edge.to_id == END_NODE:
                        continue
                    if edge.to_id not in result:
                        result.add(edge.to_id)
                        next_ids.add(edge.to_id)
            current_ids = next_ids
        return result

    def resolve_node_id(self, token: str) -> Optional[str]:
        """把用户输入的节点标识解析为图内唯一的节点 id。

        先精确匹配 id，再匹配 label（如「从 步骤B 开始执行」→ step_b）。
        匹配不到返回 None。
        """
        key = (token or "").strip()
        if not key:
            return None
        if key in self.nodes:
            return key
        for node in self.nodes.values():
            if (node.label or "").strip() == key:
                return node.id
        return None

    def is_entry_node(self, node_id: str) -> bool:
        """是否为图的 entry 起始节点。"""
        key = (node_id or "").strip()
        return bool(key) and key == self.entry_node_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [self._node_to_dict(n) for n in self.nodes.values()],
            "edges": [
                {"from": e.from_id, "to": e.to_id, "condition": e.condition.value}
                for e in self.edges
            ],
            "entry": self.entry_node_id,
        }

    @staticmethod
    def _node_to_dict(node: GraphNode) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": node.id,
            "label": node.label,
            "task": node.task,
            "max_iterations": node.max_iterations,
            "executor": node.executor.to_dict(),
        }
        return payload

    def format_summary(self) -> str:
        """向用户展示编排方案（mermaid 流程图 + 节点列表）。"""
        lines = ["```mermaid", "flowchart TD"]
        for edge in self.edges:
            if edge.from_id in (START_NODE, END_NODE) or edge.to_id in (START_NODE, END_NODE):
                continue
            lines.append(f"  {edge.from_id} -->|{edge.condition.value}| {edge.to_id}")
        lines.append("```")
        for node in self.nodes.values():
            lines.append(f"- **{node.label}** (`{node.id}`) → `{node.executor.agent_type}`")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["DirectExecGraph"]:
        nodes: Dict[str, GraphNode] = {}
        for raw in data.get("nodes") or []:
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("id") or "").strip()
            if not node_id:
                continue
            node = GraphNode(
                id=node_id,
                label=str(raw.get("label") or node_id),
                task=str(raw.get("task") or ""),
                max_iterations=int(raw.get("max_iterations") or 3),
                executor=GraphNodeExecutor.from_dict(raw.get("executor")),
            )
            nodes[node_id] = node
        edges: List[GraphEdge] = []
        for raw in data.get("edges") or []:
            if not isinstance(raw, dict):
                continue
            condition_raw = str(raw.get("condition") or "always").strip().lower()
            try:
                condition = EdgeCondition(condition_raw)
            except ValueError:
                return None
            
            from_id = str(raw.get("from") or "").strip()
            to_id = str(raw.get("to") or "").strip()
            if not from_id or not to_id:
                return None
            
            edges.append(
                GraphEdge(
                    from_id=from_id,
                    to_id=to_id,
                    condition=condition,
                )
            )
        entry_node_id = str(data.get("entry") or "").strip()
        graph = cls(nodes=nodes, edges=edges, entry_node_id=entry_node_id)
        if not graph.is_valid():
            return None
        return graph

#===============
# 任务计划图谱
#===============
PLAN_GRAPH_METADATA_KEY = "plan_graph"

class PlanGraphPhase(str, Enum):
    """编排会话阶段；序列化到 metadata 时使用 value 字符串。"""
    IDLE = "idle"
    EXECUTING = "executing"
    DONE = "done"

    @staticmethod
    def parse(raw: Any) -> "PlanGraphPhase":
        if isinstance(raw, PlanGraphPhase):
            return raw
        text = str(raw or "").strip().lower()
        try:
            return PlanGraphPhase(text)
        except ValueError:
            return PlanGraphPhase.IDLE

@dataclass
class PlanGraphState:
    """跨轮次保存：阶段、目标、图快照、各节点产出与驳回反馈。"""
    user_goal: str = ""
    plan_graph: Optional[DirectExecGraph] = None
    phase: PlanGraphPhase = PlanGraphPhase.IDLE
    running_node_ids: List[str] = field(default_factory=list)   # 正在执行的节点 id（并行时多个）
    node_session_id: Dict[str, str] = field(default_factory=dict)  # 节点 Harness 子 session id
    node_iterations: Dict[str, int] = field(default_factory=dict)  # 节点重试次数，key: 节点id, value: 重试次数
    node_outputs: Dict[str, str] = field(default_factory=dict)   # 节点产出，key: 节点id, value: 产出
    pre_node_reject_infos: Dict[str, str] = field(default_factory=dict) # 上游驳回修订意见，key返工执行节点 id；value=reject 边源节点（审查步）写入的驳回说明


    def resolve_graph(self) -> Optional[DirectExecGraph]:
        raw = self.plan_graph
        if isinstance(raw, DirectExecGraph):
            return raw
        if isinstance(raw, dict):
            graph = DirectExecGraph.from_dict(raw)
            if graph is not None:
                self.plan_graph = graph
            return graph
        return None

    def plan_graph_topology_dict(self) -> Optional[Dict[str, Any]]:
        """编排拓扑快照（含各节点 executor），写入 Session metadata.plan_graph.plan_graph。"""
        graph = self.resolve_graph()
        if graph is None:
            if isinstance(self.plan_graph, dict):
                return dict(self.plan_graph)
            return None
        return graph.to_dict()

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "plan_graph": self.plan_graph_topology_dict(),
            "phase": self.phase.value,
            "running_node_ids": self.running_node_ids,
            "node_outputs": self.node_outputs,
            "pre_node_reject_infos": self.pre_node_reject_infos,
            "node_iterations": self.node_iterations,
            "node_session_id": self.node_session_id,
        }

    @classmethod
    def from_metadata(cls, meta: Dict[str, Any]) -> Optional["PlanGraphState"]:
        raw = meta.get(PLAN_GRAPH_METADATA_KEY)
        if not isinstance(raw, dict):
            return None
        plan_graph_raw = raw.get("plan_graph")
        plan_graph = DirectExecGraph.from_dict(plan_graph_raw) if isinstance(plan_graph_raw, dict) else None
        node_session_id = dict(raw.get("node_session_id") or {})
        return cls(
            user_goal=str(raw.get("user_goal") or ""),
            plan_graph=plan_graph,
            phase=PlanGraphPhase.parse(raw.get("phase")),
            running_node_ids=list(raw.get("running_node_ids") or []),
            node_outputs=dict(raw.get("node_outputs") or {}),
            pre_node_reject_infos=dict(raw.get("pre_node_reject_infos") or {}),
            node_iterations={str(k): int(v) for k, v in (raw.get("node_iterations") or {}).items()},
            node_session_id=node_session_id,
        )

    def clear_history(self, clear_session_id: bool = True) -> None:
        '''仅仅保留图，执行记录清空'''
        self.phase = PlanGraphPhase.IDLE
        self.running_node_ids = []
        self.node_outputs = {}
        self.pre_node_reject_infos = {}
        self.node_iterations = {}
        if clear_session_id:
            self.node_session_id = {}

    def clear_node_execution_record(self, node_id: str, *, clear_session_id: bool = False) -> None:
        """清除单个节点的执行记录：产出、驳回意见、重试次数；可选清除 node_session_id。"""
        key = (node_id or "").strip()
        if not key:
            return
        self.node_outputs.pop(key, None)
        self.pre_node_reject_infos.pop(key, None)
        self.node_iterations.pop(key, None)
        if clear_session_id:
            self.node_session_id.pop(key, None)

    def clear_execution_from_node(self, node_id: str) -> None:
        """保留上游产出，清除指定节点及其下游的执行记录。"""
        graph = self.resolve_graph()
        if graph is None:
            return
        affected = {node_id} | graph.downstream(node_id)
        for nid in affected:
            self.clear_node_execution_record(nid)
        self.running_node_ids = []
