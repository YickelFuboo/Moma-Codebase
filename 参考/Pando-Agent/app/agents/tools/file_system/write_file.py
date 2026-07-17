import logging
from pathlib import Path
from typing import Any, Dict
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ..utils import _trim_diff,_two_files_patch
from ..file_state import FILE_STATE_MANAGER
from ...contants import MEMORY_DIR_NAME
from ...schemes import AgentContext, RuntimeContext


@register_tool(name="write_file", toolset="filesystem")
class WriteFileTool(BaseTool):
    """Write content to a file."""

    @property
    def name(self) -> str:
        return "write_file"   

    @property
    def description(self) -> str:
        return f"""Writes content to a file on the local filesystem.

Usage:
- Provide the target file with `path`.
- `mode='w'` overwrites the file (or creates it if missing); `mode='a'` appends content for chunked writes.
- Parent directories are created automatically if needed.
- If this is an existing file, read it first before writing to avoid accidental loss.
- Prefer editing existing files; do not create new files unless required by the task.
- Agent long-term memory: write to `<workspace>/{MEMORY_DIR_NAME}/<agent_type>/MEMORY.md` (not `<workspace>/{MEMORY_DIR_NAME}/MEMORY.md`; the latter is workspace-level auto-consolidation only).
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked.
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to write to."
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file. Prefer to keep each write chunk small to avoid tool call truncation.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["w","a"],
                    "description": "w=overwrite (first chunk), a=append (subsequent chunks). Default is w."
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
        mode: str = "w"
    ) -> ToolResult:
        try:
            if not path or not path.strip() or content is None:
                logging.error("Invalid parameters: path=%r, content=%r", path, content)
                return ToolErrorResult("Missing path or content parameter")     

            open_mode = "a" if mode == "a" else "w"
            target_path = Path(path).expanduser()
            warning = FILE_STATE_MANAGER.check_stale_and_get_warning(run_ctx.actor_id, str(target_path))
            async with FILE_STATE_MANAGER.get_path_lock(target_path) as resolved_path:
                file_path = Path(resolved_path)
                existed = file_path.exists()
                if existed and not file_path.is_file():
                    logging.error("Not a file: path=%s", file_path)
                    return ToolErrorResult(f"Not a file: {path}")
                old_content = ""
                if existed and file_path.is_file():
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        old_content = f.read()

                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, open_mode, encoding="utf-8") as f:
                    f.write(content)

                new_content = ""
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    new_content = f.read()

                diff = _trim_diff(
                    _two_files_patch(str(file_path), str(file_path), old_content, new_content)
                )

                action = "appended" if open_mode == "a" else "written"
                output = "\n".join([
                    f"<path>{file_path}</path>",
                    "<content>",
                    f"Successfully {action} {len(content)} bytes to {file_path} (mode={open_mode})",
                    "</content>",
                    f"<exists>{str(existed).lower()}</exists>",
                    f"<mode>{open_mode}</mode>",
                    "<diff>",
                    diff,
                    "</diff>",
                ])
                FILE_STATE_MANAGER.record_write(run_ctx.actor_id, file_path)
                return ToolSuccessResult(FILE_STATE_MANAGER.append_warning(output, warning))
            
        except Exception as e:
            logging.error("Failed to write file: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to write file: {str(e)}") 
