from abc import ABC, abstractmethod
from typing import Any, Dict
from ..schemes import AgentContext, RuntimeContext
from .schemes import ToolResult


class BaseTool(ABC):
    """工具基类"""

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
        
    @property
    @abstractmethod
    def parameters(self, **kwargs: Any) -> Dict[str, Any]:
        """工具参数定义
        
        Returns:
            Dict[str, Dict[str, str]]: {
                "param_name": {
                    "type": "参数类型",
                    "description": "参数描述"
                }
            }
        """
        pass

    @property
    @abstractmethod
    def is_readonly(self) -> bool:
        """是否只读：execute 不修改工作区文件、不对外部系统产生写/调度副作用。"""
        pass

    @property
    @abstractmethod
    def is_parallel(self) -> bool:
        """是否可与其他工具并行执行；要求彼此无共享可变状态。"""
        pass

    @abstractmethod
    async def execute(self, agent_ctx: AgentContext, run_ctx: RuntimeContext, **kwargs: Any) -> ToolResult:
        """执行工具调用
        
        Args:
            agent_ctx: 代理上下文
            runtime_ctx: 运行时上下文
            kwargs: 工具参数

        Returns:
            ToolResult: 工具执行结果
        """
        pass

    def to_param(self) -> Dict:
        """Convert tool to function call format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
    
    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate tool parameters against JSON schema. Returns error list (empty if valid)."""
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        t, label = schema.get("type"), path or "parameter"
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]
        
        errors = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + '.' + k if path else k))
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"))
        return errors