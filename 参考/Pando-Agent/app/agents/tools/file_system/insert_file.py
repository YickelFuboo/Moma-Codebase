import logging
from pathlib import Path
from typing import Any, Dict, Optional
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ..utils import _trim_diff,_two_files_patch
from ..file_state import FILE_STATE_MANAGER
from ...schemes import AgentContext, RuntimeContext


@register_tool(name="insert_file", toolset="filesystem")
class InsertFileTool(BaseTool):
    """Insert content into a file."""

    @property
    def name(self) -> str:
        return "insert_file"   
        
    @property
    def description(self) -> str:
        return """Insert content into a file at the given line position.

Usage:
- Provide the target file with `path`.
- `position` is optional; if omitted, content is inserted at the end of the file.
- If provided, `position` must be between 0 and the current line count.
- Returns a unified diff in `<diff>` to help verify the exact change."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to insert content into."
                },
                "content": {
                    "type": "string",
                    "description": "The content to insert into the file."
                },
                "position": {
                    "type": "integer",
                    "description": "The line number to insert content at. If None, will insert at end of file."
                }
            },
            "required": ["path", "content"]
        }      

            
    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallel(self) -> bool:
        return True

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        path: str,
        content: str,
        position: Optional[int] = None
    ) -> ToolResult:
        try:
            if not path or not path.strip() or content is None:
                logging.error("Invalid parameters: path=%r, content=%r", path, content)
                return ToolErrorResult("Invalid parameters")     
            
            warning = FILE_STATE_MANAGER.check_stale_and_get_warning(run_ctx.actor_id, path)
            async with FILE_STATE_MANAGER.get_path_lock(path) as resolved_path:
                file_path = Path(resolved_path)
                if not file_path.exists():
                    logging.error("File not found: %s", file_path)
                    return ToolErrorResult("File not found")

                if not file_path.is_file():
                    logging.error("Not a file: %s", file_path)
                    return ToolErrorResult("Not a file")

                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                if position is None:
                    position = len(lines)
                elif position < 0 or position > len(lines):
                    logging.error(
                        "Invalid position: %d, file has %d lines", position, len(lines)
                    )
                    return ToolErrorResult(f"Invalid position: {position}, file has {len(lines)} lines")

                old_content = "".join(lines)
                insert_content = content if content.endswith("\n") else content + "\n"
                new_lines = lines[:position] + [insert_content] + lines[position:]
                new_content = "".join(new_lines)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                diff = _trim_diff(
                    _two_files_patch(str(file_path), str(file_path), old_content, new_content)
                )
                output = "\n".join([
                    f"<path>{file_path}</path>",
                    "<content>",
                    f"Successfully inserted {len(content)} bytes at line {position} in file {path}",
                    "</content>",
                    f"<position>{position}</position>",
                    "<diff>",
                    diff,
                    "</diff>",
                ])
                FILE_STATE_MANAGER.record_write(run_ctx.actor_id, file_path)
                return ToolSuccessResult(FILE_STATE_MANAGER.append_warning(output, warning))
            
        except Exception as e:
            logging.error("Failed to insert content: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to insert content: {str(e)}") 