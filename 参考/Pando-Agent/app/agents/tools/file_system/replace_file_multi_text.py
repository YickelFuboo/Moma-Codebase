import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..catalog import register_tool 
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ..utils import _trim_diff,_two_files_patch,not_found_message
from ..file_state import FILE_STATE_MANAGER
from ...schemes import AgentContext, RuntimeContext


@register_tool(name="replace_file_multi_text", toolset="filesystem")
class MultiReplaceTextTool(BaseTool):
    """Apply multiple replace_file_text operations sequentially."""

    @property
    def name(self) -> str:
        return "replace_file_multi_text"

    @property
    def description(self) -> str:
        return """Performs multiple text replacements sequentially in one file.

Usage:
- Provide a single target file with `path`.
- Provide `edits` as an array of `{old_text, new_text, replaceAll?}` operations.
- Edits are applied in order; later edits see the result of earlier edits.
- The operation is atomic: if any edit fails, no changes are written."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_text": {
                                "type": "string",
                                "description": "The exact text to find"
                            },
                            "new_text": {
                                "type": "string",
                                "description": "The text to replace with"
                            },
                            "replaceAll": {
                                "type": "boolean",
                                "description": "Replace all occurrences (default false)"
                            }
                        },
                        "required": ["old_text", "new_text"]
                    },
                    "minItems": 1,
                    "description": "Array of replacements to apply sequentially"
                }
            },
            "required": ["path", "edits"]
        }

    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallel(self) -> bool:
        return False

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        path: str,
        edits: List[Dict[str, Any]]
    ) -> ToolResult:
        try:
            if not edits:
                return ToolErrorResult("Provide at least one edit")
            if not path or not path.strip():
                return ToolErrorResult("Missing path parameter")
            
            warning = FILE_STATE_MANAGER.check_stale_and_get_warning(run_ctx.actor_id, path)
            async with FILE_STATE_MANAGER.get_path_lock(path) as resolved_path:
                file_path = Path(resolved_path)
                if not file_path.exists():
                    return ToolErrorResult(f"File not found: {path}")
                if not file_path.is_file():
                    return ToolErrorResult(f"Not a file: {path}")
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    original_content = f.read()

                working_content = original_content
                step_results: List[Dict[str, Any]] = []
                total_replaced = 0
                for idx, edit in enumerate(edits, start=1):
                    old_text = edit.get("old_text")
                    new_text = edit.get("new_text")
                    replace_all = edit.get("replaceAll")
                    next_content, replaced_count, err = self._apply_single_edit(
                        path=path,
                        content=working_content,
                        old_text=old_text,
                        new_text=new_text,
                        replace_all=replace_all,
                    )
                    if err:
                        return ToolErrorResult(f"multi_replace_text stopped at edit {idx}: {err}")
                    working_content = next_content
                    total_replaced += replaced_count
                    step_results.append({"index": idx, "replaced": replaced_count})

                if working_content == original_content:
                    return ToolErrorResult("No changes to apply.")

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(working_content)

                diff = _trim_diff(
                    _two_files_patch(str(file_path), str(file_path), original_content, working_content)
                )
                output = "\n".join([
                    f"<path>{file_path}</path>",
                    "<content>",
                    f"Successfully edited {path} with {len(edits)} sequential edit(s), replaced {total_replaced} occurrence(s)",
                    "</content>",
                    "<diff>",
                    diff,
                    "</diff>",
                ])
                FILE_STATE_MANAGER.record_write(run_ctx.actor_id, file_path)
                return ToolSuccessResult(FILE_STATE_MANAGER.append_warning(output, warning), metadata={"results": step_results})
        except Exception as e:
            logging.error("Failed to execute multi_replace_text: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to execute multi_replace_text: {str(e)}")

    @staticmethod
    def _apply_single_edit(
        path: str,
        content: str,
        old_text: Any,
        new_text: Any,
        replace_all: Optional[bool],
    ) -> tuple[str, int, Optional[str]]:
        if old_text is None or new_text is None:
            return content, 0, "Missing old_text or new_text parameter"
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            return content, 0, "old_text and new_text must be strings"
        if old_text == "":
            return content, 0, "old_text must not be empty. Use write_file for full overwrite."
        if old_text == new_text:
            return content, 0, "No changes to apply: old_text and new_text are identical."
        if old_text not in content:
            return content, 0, not_found_message(old_text, content, path)
        
        count = content.count(old_text)
        if count > 1 and not replace_all:
            return content, 0, (
                f"old_text appears {count} times. Please provide more context to make it unique or set replaceAll=true."
            )
        
        # Ö´ÐÐÌæ»»²Ù×÷
        if replace_all:
            return content.replace(old_text, new_text), count, None
        return content.replace(old_text, new_text, 1), 1, None

