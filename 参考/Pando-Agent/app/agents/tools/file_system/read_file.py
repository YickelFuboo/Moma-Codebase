import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ..file_state import FILE_STATE_MANAGER
from ...schemes import AgentContext, RuntimeContext
from .utils import format_not_found_message
from .image_common import (
    IMAGE_SUFFIXES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_BYTES_LABEL,
    describe_image_file,
    format_image_read_output,
    image_file_metadata,
    is_image_file,
)
from .pdf_common import extract_pdf_lines


DEFAULT_READ_LIMIT = 2000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 50 * 1024
MAX_BYTES_LABEL = f"{MAX_BYTES // 1024} KB"


def _is_probably_binary(ext: str, size: int, head: bytes) -> bool:
    ext = ext.lower()
    if ext == ".pdf" or ext in IMAGE_SUFFIXES:
        return False
    if ext in {
        ".zip", ".tar", ".gz", ".exe", ".dll", ".so", ".class", ".jar", ".war", ".7z",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
        ".bin", ".dat", ".obj", ".o", ".a", ".lib", ".wasm", ".pyc", ".pyo",
    }:
        return True
    if size == 0:
        return False
    if head.startswith(b"%PDF"):
        return False
    if b"\x00" in head:
        return True
    non_printable = 0
    for b in head:
        if b < 9 or (b > 13 and b < 32):
            non_printable += 1
    return non_printable / max(1, len(head)) > 0.3


def _load_file_lines(file_path: Path) -> List[str]:
    if file_path.suffix.lower() == ".pdf":
        return extract_pdf_lines(file_path)
    lines: List[str] = []
    with open(file_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for line in f:
            lines.append(line.rstrip("\n\r"))
    return lines


def _paginate_lines(
    lines: List[str],
    *,
    offset: int,
    limit: int,
) -> tuple[str, bool, int]:
    total_lines = len(lines)
    off = offset
    lim = limit
    raw: List[str] = []
    bytes_count = 0
    has_more = False
    truncated_by_bytes = False

    for idx, text in enumerate(lines, 1):
        if idx < off:
            continue
        if len(raw) >= lim:
            has_more = True
            break
        if len(text) > MAX_LINE_LENGTH:
            text = text[:MAX_LINE_LENGTH] + f"... (line truncated to {MAX_LINE_LENGTH} chars)"
        add = len(text.encode("utf-8")) + (1 if raw else 0)
        if bytes_count + add > MAX_BYTES:
            truncated_by_bytes = True
            has_more = True
            break
        raw.append(text)
        bytes_count += add

    if total_lines < off and not (total_lines == 0 and off == 1):
        raise ValueError(f"Offset {off} is out of range for this file ({total_lines} lines)")

    numbered = [f"{i + off}: {t}" for i, t in enumerate(raw)]
    content = "\n".join(numbered)
    last_read = off + len(raw) - 1 if raw else off - 1
    next_offset = last_read + 1
    truncated = has_more or truncated_by_bytes

    if truncated_by_bytes:
        content += (
            f"\n\n(Output capped at {MAX_BYTES_LABEL}. Showing lines {off}-{last_read}. "
            f"Use offset={next_offset} to continue.)"
        )
    elif has_more:
        content += (
            f"\n\n(Showing lines {off}-{last_read} of {total_lines}. "
            f"Use offset={next_offset} to continue.)"
        )
    else:
        content += f"\n\n(End of file - total {total_lines} lines)"

    return content, truncated, next_offset


@register_tool(name="read_file", toolset="filesystem")
class ReadFileTool(BaseTool):
    """文件读取工具"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return """Read a file from the local filesystem. If the path does not exist, similar paths may be suggested.

Usage:
- The path parameter should be an absolute path.
- Supports plain text files, `.pdf` (text extraction), and common image formats (PNG, JPEG, GIF, WebP, BMP, TIFF, ICO).
- For images, content is produced by the configured CV model in `data/models/cv_models.json` (vision description).
- By default, this tool returns up to 2000 lines from the start of the file.
- The offset parameter is the line number to start from (1-indexed).
- To read later sections, call this tool again with a larger offset.
- Use the grep tool to find specific content in large files or files with long lines.
- If you are unsure of the correct file path, use the glob tool to look up filenames by glob pattern.
- Contents are returned with each line prefixed by its line number as `<line>: <content>`.
- Any line longer than 2000 characters is truncated.
- Call this tool in parallel when you know there are multiple files you want to read.
- Avoid tiny repeated slices (30 line chunks). If you need more context, read a larger window."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to read."
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional line number to start reading from (1-indexed)."
                },
                "limit": {
                    "type": "integer",
                    "description": f"Optional maximum number of lines to read. Default is {DEFAULT_READ_LIMIT}."
                },
                "vision_prompt": {
                    "type": "string",
                    "description": "Optional prompt for image files only (e.g. 'extract all text in the screenshot'). Ignored for text/PDF."
                }
            },
            "required": ["path"]
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
        limit: Optional[int] = None,
        vision_prompt: Optional[str] = None,
    ) -> ToolResult:
        try:
            if not path or not path.strip():
                logging.error("参数错误: path=%r", path)
                return ToolErrorResult("Missing path parameter")

            if offset is not None and offset < 1:
                return ToolErrorResult("offset must be greater than or equal to 1")

            if limit is not None and limit < 1:
                return ToolErrorResult("limit must be greater than or equal to 1")

            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.warning("文件不存在: path=%s", file_path)
                return ToolErrorResult(format_not_found_message(path, file_path))

            if not file_path.is_file():
                logging.warning("不是文件路径: path=%s", file_path)
                return ToolErrorResult(f"Not a file: {path}")

            size = file_path.stat().st_size

            if is_image_file(file_path):
                if size > MAX_IMAGE_BYTES:
                    return ToolErrorResult(
                        f"Image too large ({size} bytes). Maximum is {MAX_IMAGE_BYTES_LABEL}: {path}"
                    )
                try:
                    metadata = image_file_metadata(file_path)
                    cv_result = await describe_image_file(
                        file_path,
                        prompt=vision_prompt,
                        run_ctx=run_ctx,
                    )
                    if cv_result is None:
                        if run_ctx.is_aborted():
                            return run_ctx.aborted_tool_result(self.name)
                        return ToolErrorResult("Failed to read image: no vision result")
                    description, model_label = cv_result
                except Exception as e:
                    logging.error("读取图片异常: path=%r, error=%s", path, e)
                    return ToolErrorResult(f"Failed to read image: {e}")
                output = format_image_read_output(file_path, metadata, description, model_label)
                FILE_STATE_MANAGER.record_read(run_ctx.actor_id, file_path, partial=False)
                return ToolSuccessResult(output)

            with open(file_path, "rb") as f:
                head = f.read(min(4096, size or 0))
            if _is_probably_binary(file_path.suffix, size, head):
                return ToolErrorResult(f"Cannot read binary file: {path}")

            off = offset or 1
            lim = limit or DEFAULT_READ_LIMIT
            lines = _load_file_lines(file_path)
            content, truncated, next_offset = _paginate_lines(lines, offset=off, limit=lim)

            output = "\n".join([
                f"<path>{file_path}</path>",
                "<content>",
                content,
                "</content>",
                f"<truncated>{str(truncated).lower()}</truncated>",
                f"<next_offset>{next_offset if truncated else ''}</next_offset>",
            ])
            partial = off > 1 or truncated
            FILE_STATE_MANAGER.record_read(run_ctx.actor_id, file_path, partial=partial)
            return ToolSuccessResult(output)

        except ValueError as e:
            return ToolErrorResult(str(e))
        except Exception as e:
            logging.error("读取文件异常: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to read file: {str(e)}")
