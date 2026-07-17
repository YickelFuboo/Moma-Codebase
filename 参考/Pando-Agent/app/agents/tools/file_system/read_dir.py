import logging
from pathlib import Path
from typing import Any, Optional
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ...schemes import AgentContext, RuntimeContext


DEFAULT_READ_LIMIT = 2000


@register_tool(name="read_dir", toolset="filesystem")
class ReadDirTool(BaseTool):
    """Read directory entries with optional offset and limit."""

    @property
    def name(self) -> str:
        return "read_dir"

    @property
    def description(self) -> str:
        return f"""Read a directory from the local filesystem. If the path does not exist, an error is returned.

Usage:
- The path parameter should be an absolute path.
- By default, this tool returns up to {DEFAULT_READ_LIMIT} entries from the start of the directory.
- The offset parameter is the entry number to start from (1-indexed).
- To read later sections, call this tool again with a larger offset.
- Entries are returned one per line with a trailing `/` for subdirectories.
- Call this tool in parallel when you know there are multiple directories you want to read."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional entry number to start from (1-indexed).",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Optional maximum number of entries to read. Default is {DEFAULT_READ_LIMIT}.",
                },
            },
            "required": ["path"],
        }

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallel(self) -> bool:
        return True

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        path: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None
    ) -> ToolResult:
        try:
            if not path or not path.strip():
                return ToolErrorResult("Missing path parameter")

            if offset is not None and offset < 1:
                return ToolErrorResult("offset must be greater than or equal to 1")

            if limit is not None and limit < 1:
                return ToolErrorResult("limit must be greater than or equal to 1")

            dir_path = Path(path).expanduser().resolve()
            if not dir_path.exists():
                return ToolErrorResult(f"Directory not found: {path}")

            if not dir_path.is_dir():
                return ToolErrorResult(f"Not a directory: {path}")

            entries = []
            for child in sorted(dir_path.iterdir(), key=lambda p: p.name.lower()):
                if child.is_dir():
                    entries.append(child.name + "/")
                else:
                    entries.append(child.name)

            off = offset or 1
            lim = limit or DEFAULT_READ_LIMIT
            start = off - 1
            sliced = entries[start:start + lim]

            if start >= len(entries) and not (len(entries) == 0 and start == 0):
                return ToolErrorResult(
                    f"Offset {off} is out of range for this directory ({len(entries)} entries)"
                )

            truncated = start + len(sliced) < len(entries)
            output = "\n".join([
                f"<path>{dir_path}</path>",
                "<content>",
                "\n".join(sliced),
                "</content>",
                f"<truncated>{str(truncated).lower()}</truncated>",
                f"<next_offset>{off + len(sliced) if truncated else ''}</next_offset>",
            ])
            return ToolSuccessResult(output)
        except PermissionError as e:
            logging.error("Permission error reading directory: path=%s, error=%s", path, e)
            return ToolErrorResult(f"Error: {e}")
        except Exception as e:
            logging.error("Error reading directory: path=%s, error=%s", path, e)
            return ToolErrorResult(f"Error reading directory: {str(e)}")
