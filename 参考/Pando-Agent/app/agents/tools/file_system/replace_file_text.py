import difflib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ..utils import _trim_diff,_two_files_patch,not_found_message
from ..file_state import FILE_STATE_MANAGER
from ...schemes import AgentContext, RuntimeContext


@register_tool(name="replace_file_text", toolset="filesystem")
class ReplaceFileTextTool(BaseTool):
    """Replace text in a file."""

    @property
    def name(self) -> str:
        return "replace_file_text"
    
    @property
    def description(self) -> str:
        return """Performs exact string replacements in files.

Usage:
- Provide the target file with `path`.
- You should read the file before editing to avoid accidental mismatches.
- Match `old_text` exactly as it appears in file content (including spaces/indentation).
- Prefer editing existing files. Do not create new files unless required.
- Only use emojis if the user explicitly requests it.
- The edit fails if `old_text` is not found in the file.
- By default, this tool replaces a single unique match.
- The edit fails if `old_text` appears multiple times and `replaceAll` is not true.
- When multiple matches exist, either provide more surrounding context in `old_text` or set `replaceAll=true`.
- Use `replaceAll` for file-wide renaming/replacement operations.
- Use `write_file` for full-file overwrite; `old_text` must not be empty in this tool."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                },
                "replaceAll": {
                    "type": "boolean",
                    "description": "Replace all occurrences of old_text (default false)"
                }
            },
            "required": ["path", "old_text", "new_text"]
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
        old_text: str,
        new_text: str,
        replaceAll: Optional[bool] = None
    ) -> ToolResult:
        try:
            if not path or not path.strip() or old_text is None or new_text is None:
                logging.error("Invalid parameters: path=%r, old_text=%r, new_text=%r", path, old_text, new_text)
                return ToolErrorResult("Missing path, old_text or new_text parameter")
            if old_text == "":
                return ToolErrorResult("old_text must not be empty. Use write_file for full overwrite.")
            if old_text == new_text:
                return ToolErrorResult("No changes to apply: old_text and new_text are identical.")

            warning = FILE_STATE_MANAGER.check_stale_and_get_warning(run_ctx.actor_id, path)
            async with FILE_STATE_MANAGER.get_path_lock(path) as resolved_path:
                file_path = Path(resolved_path)
                if not file_path.exists():
                    logging.warning("File not found: path=%s", file_path)
                    return ToolErrorResult(f"File not found: {path}")

                if not file_path.is_file():
                    logging.warning("Not a file: path=%s", file_path)
                    return ToolErrorResult(f"Not a file: {path}")

                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                if old_text not in content:
                    logging.warning(
                        "old_text not found in content: old_text=%r, path=%s",
                        old_text,
                        file_path,
                    )
                    return ToolErrorResult(not_found_message(old_text, content, path))

                count = content.count(old_text)
                if count > 1 and not replaceAll:
                    logging.warning(
                        "old_text appears %d times in %s. Please provide more context.",
                        count,
                        file_path,
                    )
                    return ToolErrorResult(
                        f"old_text appears {count} times. Please provide more context to make it unique or set replaceAll=true."
                    )

                if replaceAll:
                    new_content = content.replace(old_text, new_text)
                    replaced_count = count
                else:
                    new_content = content.replace(old_text, new_text, 1)
                    replaced_count = 1
                if new_content == content:
                    return ToolErrorResult("No changes to apply.")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                diff = _trim_diff(
                    _two_files_patch(str(file_path), str(file_path), content, new_content)
                )
                output = "\n".join([
                    f"<path>{file_path}</path>",
                    "<content>",
                    f"Successfully edited {path} (replaced {replaced_count} occurrence{'s' if replaced_count != 1 else ''})",
                    "</content>",
                    "<diff>",
                    diff,
                    "</diff>",
                ])
                FILE_STATE_MANAGER.record_write(run_ctx.actor_id, file_path)
                return ToolSuccessResult(FILE_STATE_MANAGER.append_warning(output, warning))
        except PermissionError as e:
            logging.error("Permission error: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Permission error: {str(e)}")
        except Exception as e:
            logging.error("Failed to edit file: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to edit file: {str(e)}")

