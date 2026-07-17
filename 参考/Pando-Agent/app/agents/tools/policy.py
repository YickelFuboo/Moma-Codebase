"""工具权限策略：将 config permissions / toolset / mode / spawn 参数解析为工具名列表。"""
from __future__ import annotations
import logging
from typing import Any, Dict, FrozenSet, List, Optional, Set
from .catalog import (
    catalog_tool_is_readonly,
    catalog_tool_names,
    catalog_toolsets,
    tool_names_for_toolset,
)


DELEGATION_TOOL_NAME = "spawn"
SUBAGENT_TOOLSET = "subagent"

SUBAGENT_HARD_DENIED_TOOLS: FrozenSet[str] = frozenset(
    {
        DELEGATION_TOOL_NAME,
        "ask_question",
        "terminate",
        "cron",
        "todo_read",
        "todo_write",
    }
)

class ToolPolicyResolver:
    """统一解析主 Agent / 子 Agent 可用工具名（不含 MCP，MCP 仍按 server 白名单注册）。"""

    @staticmethod
    def _expand_tools_from_toolsets(toolsets: List[str]) -> Set[str]:
        """将 toolset 名列表展开为对应的内建工具名集合。"""
        names: Set[str] = set()
        for ts in toolsets:
            key = (ts or "").strip()
            if not key:
                continue
            names.update(tool_names_for_toolset(key))
        return names

    @staticmethod
    def _decision_is_allow(decision: Any) -> bool:
        """配置项是否为 allow。"""
        return str(decision or "").strip().lower() == "allow"

    @staticmethod
    def _decision_is_deny(decision: Any) -> bool:
        """配置项是否为 deny。"""
        return str(decision or "").strip().lower() == "deny"

    @staticmethod
    def _get_permissions_maps(permissions: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """从 permissions 取出并规范化 toolsets / tools 两层映射。"""
        toolsets_map = permissions.get("toolsets")
        tools_map = permissions.get("tools")
        if not isinstance(toolsets_map, dict):
            toolsets_map = {}
        if not isinstance(tools_map, dict):
            tools_map = {}
        return toolsets_map, tools_map

    @classmethod
    def _resolve_toolsets_map(
        cls,
        toolsets_map: Dict[str, Any],
        *,
        all_toolsets: Set[str],
    ) -> tuple[Set[str], Set[str]]:
        """解析 toolsets 层的 allow/deny，返回应加入白名单与应排除的工具名集合。"""
        allowed: Set[str] = set()
        denied: Set[str] = set()
        for key, decision in toolsets_map.items():
            name = str(key).strip()
            if not name:
                continue
            if name not in all_toolsets:
                logging.warning("tool policy: unknown toolset %r, skipped", name)
                continue
            if cls._decision_is_allow(decision):
                allowed.update(tool_names_for_toolset(name))
            elif cls._decision_is_deny(decision):
                denied.update(tool_names_for_toolset(name))
        return allowed, denied

    @classmethod
    def _resolve_tools_map(
        cls,
        tools_map: Dict[str, Any],
        *,
        all_tools: Set[str],
    ) -> tuple[Set[str], Set[str]]:
        """解析 tools 层的 allow/deny，返回应加入白名单与应排除的单工具名集合。"""
        allowed: Set[str] = set()
        denied: Set[str] = set()
        for key, decision in tools_map.items():
            name = str(key).strip()
            if not name:
                continue
            if name not in all_tools:
                logging.warning("tool policy: unknown tool %r, skipped", name)
                continue
            if cls._decision_is_allow(decision):
                allowed.add(name)
            elif cls._decision_is_deny(decision):
                denied.add(name)
        return allowed, denied

    @classmethod
    def _resolve_tools_permissions(cls, permissions: Dict[str, Any]) -> Set[str]:
        """permissions.toolsets ∪ permissions.tools 解析为内建工具名白名单。"""
        toolsets_map, tools_map = cls._get_permissions_maps(permissions)
        all_toolsets = set(catalog_toolsets())
        all_tools = set(catalog_tool_names())

        ts_allow, ts_deny = cls._resolve_toolsets_map(toolsets_map, all_toolsets=all_toolsets)
        tool_allow, tool_deny = cls._resolve_tools_map(tools_map, all_tools=all_tools)
        return (ts_allow | tool_allow) - ts_deny - tool_deny

    @classmethod
    def resolve_agent_tools(
        cls,
        agent_config: Dict[str, Any],
    ) -> List[str]:
        """解析主 Agent 内建工具白名单；叠加 modes 下当前 mode 的收紧规则（不含 MCP）。"""
        tools_block = agent_config.get("tools") if isinstance(agent_config.get("tools"), dict) else {}
        permissions = tools_block.get("permissions") if isinstance(tools_block.get("permissions"), dict) else {}
        allow_tools = cls._resolve_tools_permissions(permissions)

        modes_cfg = agent_config.get("modes")
        if isinstance(modes_cfg, dict):
            effective_mode = str(modes_cfg.get("mode") or "default").strip().lower()
            mode_cfg = modes_cfg.get(effective_mode)
            if isinstance(mode_cfg, dict):
                deny_toolsets = mode_cfg.get("deny_toolsets") or []
                if isinstance(deny_toolsets, list):
                    for ts in deny_toolsets:
                        allow_tools -= cls._expand_tools_from_toolsets([str(ts)])
                deny_tools = mode_cfg.get("deny_tools") or []
                if isinstance(deny_tools, list):
                    allow_tools -= {str(t).strip() for t in deny_tools if str(t).strip()}

        return sorted(allow_tools)

    @classmethod
    def resolve_spawn_tools(
        cls,
        *,
        parent_tool_names: List[str],
        parent_agent_config: Dict[str, Any],
    ) -> List[str]:
        """子 Agent 工具集解析。

        父 Agent 当前工具
        − SUBAGENT_HARD_DENIED_TOOLS（代码硬底线）
        − 非 is_readonly 工具（spawn.readonly 为 true，默认 true）
        − spawn.deny_toolsets / spawn.deny_tools
        """
        tools_names = {str(n) for n in parent_tool_names if n}
        tools_names -= SUBAGENT_HARD_DENIED_TOOLS  # 硬排除

        tools_block = parent_agent_config.get("tools") if isinstance(parent_agent_config.get("tools"), dict) else {}
        spawn_cfg = tools_block.get("spawn")
        spawn_cfg = spawn_cfg if isinstance(spawn_cfg, dict) else {}

        readonly = True if "readonly" not in spawn_cfg else bool(spawn_cfg.get("readonly"))
        if readonly:
            tools_names = {n for n in tools_names if catalog_tool_is_readonly(n) is True}

        deny_toolsets: Set[str] = set()
        deny_tools: Set[str] = set()
        raw_toolsets = spawn_cfg.get("deny_toolsets")
        if isinstance(raw_toolsets, list):
            for ts in raw_toolsets:
                key = str(ts).strip()
                if key:
                    deny_toolsets |= cls._expand_tools_from_toolsets([key])
        raw_tools = spawn_cfg.get("deny_tools")
        if isinstance(raw_tools, list):
            deny_tools = {str(t).strip() for t in raw_tools if str(t).strip()}
        tools_names -= deny_toolsets
        tools_names -= deny_tools

        return sorted(tools_names)
