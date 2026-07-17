"""GraphNode 节点配置（ReAct executor）。

本模块定义 GraphNode 执行时走 Harness ReAct Agent 的配置结构，以及从
Session 拓扑 JSON 解析、序列化的方法。

配置来源（仅 Session 拓扑 / Planning 生成图）：
- 节点 JSON 的 executor 对象（ReAct：`kind` + `agent_type`）
- 未配置 executor 时默认 kind=react

拓扑节点完整示例（ReAct，默认）::

    {
      "id": "step_dev",
      "label": "开发实现",
      "task": "完成接口开发",
      "max_iterations": 3,
      "executor": {
        "kind": "react",
        "agent_type": "AiAssistant"
      }
    }
"""
from dataclasses import dataclass
from typing import Any, Dict

PLANNING_EXECUTOR_REACT = "react"


@dataclass
class GraphNodeExecutor:
    """节点执行策略：ReAct 用 agent_type 指定 Harness Agent。"""
    kind: str = PLANNING_EXECUTOR_REACT
    agent_type: str = ""

    @classmethod
    def from_react(cls, agent_type: str = "") -> "GraphNodeExecutor":
        return cls(kind=PLANNING_EXECUTOR_REACT, agent_type=agent_type)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"kind": self.kind}
        if self.agent_type:
            payload["agent_type"] = self.agent_type
        return payload

    @classmethod
    def from_dict(cls, raw: Any) -> "GraphNodeExecutor":
        """从拓扑节点 executor 子对象还原。"""
        if not isinstance(raw, dict):
            return cls.from_react()
        kind = str(raw.get("kind") or PLANNING_EXECUTOR_REACT).strip().lower()
        if kind == "cli":
            raise ValueError("CLI 执行方式已废弃，请重新生成编排方案")
        agent_type = str(raw.get("agent_type") or "").strip()
        return cls.from_react(agent_type)
