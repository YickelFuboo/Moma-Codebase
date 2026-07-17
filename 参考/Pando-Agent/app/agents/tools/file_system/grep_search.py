import asyncio
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from ..base import BaseTool
from ..catalog import register_tool
from ..schemes import ToolErrorResult, ToolResult, ToolSuccessResult
from ...schemes import AgentContext, RuntimeContext
from .utils import resolve_search_dir, rg_executable


MAX_LINE_LENGTH = 2000
_MAX_RESULTS = 100
_YIELD_EVERY_N_FILES = 32
OutputMode = Literal["content", "files_with_matches", "count"]

MatchRow = Tuple[str, float, int, str]


def _include_match(path: Path, include: Optional[str]) -> bool:
    if not include:
        return True
    inc = include
    if inc.startswith("{") and inc.endswith("}"):
        inc = "*." + inc[1:-1]
    if "{" in inc and "}" in inc:
        parts = [part.strip() for part in inc.split(",") if part.strip()]
        return any(Path(path.name).match(part) for part in parts)
    return Path(path.name).match(inc) or Path(str(path)).match(inc)


def _truncate_line(text: str) -> str:
    if len(text) > MAX_LINE_LENGTH:
        return text[:MAX_LINE_LENGTH] + "..."
    return text


def _format_content_output(matches: List[MatchRow]) -> str:
    if not matches:
        return "No files found"
    matches.sort(key=lambda x: (x[1], x[0], x[2]), reverse=True)
    truncated = len(matches) > _MAX_RESULTS
    final = matches[:_MAX_RESULTS]
    total = len(matches)
    out_lines = [f"Found {total} matches" + (f" (showing first {_MAX_RESULTS})" if truncated else "")]
    current = ""
    for fp, _, ln, text in final:
        if current != fp:
            if current:
                out_lines.append("")
            current = fp
            out_lines.append(f"{fp}:")
        out_lines.append(f"  Line {ln}: {text}")
    if truncated:
        out_lines.append("")
        out_lines.append(
            f"(Results truncated: showing {_MAX_RESULTS} of {total} matches ({total - _MAX_RESULTS} hidden). "
            "Consider using a more specific path or pattern.)"
        )
    return "\n".join(out_lines)


def _format_files_output(rows: List[Tuple[str, float]], *, total: int) -> str:
    if not rows:
        return "No files found"
    truncated = total > _MAX_RESULTS
    out_lines = [f"Found {total} files" + (f" (showing first {_MAX_RESULTS})" if truncated else "")]
    out_lines.extend(fp for fp, _ in rows)
    if truncated:
        out_lines.append("")
        out_lines.append("(Results truncated. Use a more specific path or pattern.)")
    return "\n".join(out_lines)


def _format_count_output(rows: List[Tuple[str, float, int]], *, total: int) -> str:
    if not rows:
        return "No files found"
    truncated = total > _MAX_RESULTS
    out_lines = [f"Found {total} files with matches" + (f" (showing first {_MAX_RESULTS})" if truncated else "")]
    for fp, _, count in rows:
        out_lines.append(f"{fp}: {count}")
    if truncated:
        out_lines.append("")
        out_lines.append("(Results truncated. Use a more specific path or pattern.)")
    return "\n".join(out_lines)


async def _scan_content_python(
    search: Path,
    rx: re.Pattern[str],
    include: Optional[str],
    run_ctx: RuntimeContext,
) -> Optional[List[MatchRow]]:
    matches: List[MatchRow] = []
    scanned = 0
    for fp in search.rglob("*"):
        if run_ctx.is_aborted():
            return None
        if len(matches) >= _MAX_RESULTS:
            break
        scanned += 1
        if scanned % _YIELD_EVERY_N_FILES == 0:
            await asyncio.sleep(0)
        if not fp.is_file() or not _include_match(fp, include):
            continue
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            mtime = 0.0
        try:
            with fp.open("r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, 1):
                    if rx.search(line):
                        matches.append((str(fp), mtime, idx, _truncate_line(line.rstrip("\n\r"))))
                        if len(matches) >= _MAX_RESULTS:
                            break
        except OSError:
            continue
    return matches


async def _scan_files_python(
    search: Path,
    rx: re.Pattern[str],
    include: Optional[str],
    run_ctx: RuntimeContext,
) -> Optional[Tuple[List[Tuple[str, float]], int]]:
    files: Dict[str, float] = {}
    scanned = 0
    for fp in search.rglob("*"):
        if run_ctx.is_aborted():
            return None
        if len(files) >= _MAX_RESULTS:
            break
        scanned += 1
        if scanned % _YIELD_EVERY_N_FILES == 0:
            await asyncio.sleep(0)
        if not fp.is_file() or not _include_match(fp, include):
            continue
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            mtime = 0.0
        try:
            with fp.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if rx.search(line):
                        files[str(fp)] = mtime
                        break
        except OSError:
            continue
    rows = sorted(files.items(), key=lambda x: x[1], reverse=True)
    return ([(p, m) for p, m in rows[:_MAX_RESULTS]], len(rows))


async def _scan_count_python(
    search: Path,
    rx: re.Pattern[str],
    include: Optional[str],
    run_ctx: RuntimeContext,
) -> Optional[Tuple[List[Tuple[str, float, int]], int]]:
    counts: Counter[str] = Counter()
    mtimes: Dict[str, float] = {}
    scanned = 0
    for fp in search.rglob("*"):
        if run_ctx.is_aborted():
            return None
        scanned += 1
        if scanned % _YIELD_EVERY_N_FILES == 0:
            await asyncio.sleep(0)
        if not fp.is_file() or not _include_match(fp, include):
            continue
        key = str(fp)
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            mtime = 0.0
        try:
            with fp.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if rx.search(line):
                        counts[key] += 1
                        mtimes[key] = mtime
        except OSError:
            continue
    rows = sorted(
        [(p, mtimes[p], c) for p, c in counts.items()],
        key=lambda x: (x[1], x[0]),
        reverse=True,
    )
    return (rows[:_MAX_RESULTS], len(rows))


async def _run_rg_lines(
    cmd: List[str],
    search: Path,
    run_ctx: RuntimeContext,
) -> Optional[Tuple[int, bytes]]:
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(search),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        logging.warning("grep_search: failed to start ripgrep: %s", e)
        return None

    stdout = process.stdout
    if stdout is None:
        process.kill()
        await process.wait()
        return None

    chunks: List[bytes] = []
    while True:
        if run_ctx.is_aborted():
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            return None
        line = await stdout.readline()
        if not line:
            break
        chunks.append(line)

    stderr_bytes = b""
    if process.stderr is not None:
        stderr_bytes = await process.stderr.read()
    returncode = await process.wait()
    if returncode not in (0, 1):
        err = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"ripgrep exited with code {returncode}")
    return returncode, b"".join(chunks)


async def _scan_content_ripgrep(
    search: Path,
    pattern: str,
    include: Optional[str],
    run_ctx: RuntimeContext,
) -> Optional[List[MatchRow]]:
    rg = rg_executable()
    if not rg:
        return None
    cmd: List[str] = [rg, "--json", "--line-number", "--no-heading", "--color=never"]
    if include:
        cmd.extend(["-g", include])
    cmd.extend([pattern, "."])

    result = await _run_rg_lines(cmd, search, run_ctx)
    if result is None:
        return None
    _, raw = result
    matches: List[MatchRow] = []
    mtime_cache: Dict[str, float] = {}
    for line in raw.splitlines():
        try:
            payload = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "match":
            continue
        data = payload.get("data") or {}
        fp = (data.get("path") or {}).get("text") or ""
        if not fp:
            continue
        line_number = int(data.get("line_number") or 0)
        text = _truncate_line(((data.get("lines") or {}).get("text") or "").rstrip("\n\r"))
        if fp not in mtime_cache:
            try:
                mtime_cache[fp] = Path(fp).stat().st_mtime
            except OSError:
                mtime_cache[fp] = 0.0
        matches.append((fp, mtime_cache[fp], line_number, text))
        if len(matches) >= _MAX_RESULTS:
            break
    return matches


async def _scan_files_ripgrep(
    search: Path,
    pattern: str,
    include: Optional[str],
    run_ctx: RuntimeContext,
) -> Optional[Tuple[List[Tuple[str, float]], int]]:
    rg = rg_executable()
    if not rg:
        return None
    cmd: List[str] = [rg, "-l", "--color=never", pattern, "."]
    if include:
        cmd = [rg, "-l", "--color=never", "-g", include, pattern, "."]
    result = await _run_rg_lines(cmd, search, run_ctx)
    if result is None:
        return None
    _, raw = result
    paths = [ln.decode("utf-8", errors="replace").strip() for ln in raw.splitlines() if ln.strip()]
    rows: List[Tuple[str, float]] = []
    for rel in paths:
        fp = (search / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not fp.is_file():
            fp = Path(rel)
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            mtime = 0.0
        rows.append((str(fp.resolve()), mtime))
    rows.sort(key=lambda x: x[1], reverse=True)
    return (rows[:_MAX_RESULTS], len(rows))


async def _scan_count_ripgrep(
    search: Path,
    pattern: str,
    include: Optional[str],
    run_ctx: RuntimeContext,
) -> Optional[Tuple[List[Tuple[str, float, int]], int]]:
    rg = rg_executable()
    if not rg:
        return None
    cmd: List[str] = [rg, "-c", "--color=never", pattern, "."]
    if include:
        cmd = [rg, "-c", "--color=never", "-g", include, pattern, "."]
    result = await _run_rg_lines(cmd, search, run_ctx)
    if result is None:
        return None
    _, raw = result
    rows: List[Tuple[str, float, int]] = []
    for line in raw.splitlines():
        text = line.decode("utf-8", errors="replace").strip()
        if not text or ":" not in text:
            continue
        fp_part, count_part = text.rsplit(":", 1)
        try:
            count = int(count_part.strip())
        except ValueError:
            continue
        fp = Path(fp_part.strip())
        if not fp.is_absolute():
            fp = (search / fp).resolve()
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            mtime = 0.0
        rows.append((str(fp), mtime, count))
    rows.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return (rows[:_MAX_RESULTS], len(rows))


async def _grep_execute(
    search: Path,
    pattern: str,
    rx: re.Pattern[str],
    include: Optional[str],
    output_mode: OutputMode,
    run_ctx: RuntimeContext,
) -> Optional[str]:
    try:
        if output_mode == "content":
            rg_result = await _scan_content_ripgrep(search, pattern, include, run_ctx)
            if rg_result is not None:
                return _format_content_output(rg_result)
            py_result = await _scan_content_python(search, rx, include, run_ctx)
            if py_result is None:
                return None
            return _format_content_output(py_result)

        if output_mode == "files_with_matches":
            rg_result = await _scan_files_ripgrep(search, pattern, include, run_ctx)
            if rg_result is not None:
                rows, total = rg_result
                return _format_files_output(rows, total=total)
            py_result = await _scan_files_python(search, rx, include, run_ctx)
            if py_result is None:
                return None
            rows, total = py_result
            return _format_files_output(rows, total=total)

        rg_result = await _scan_count_ripgrep(search, pattern, include, run_ctx)
        if rg_result is not None:
            rows, total = rg_result
            return _format_count_output(rows, total=total)
        py_result = await _scan_count_python(search, rx, include, run_ctx)
        if py_result is None:
            return None
        rows, total = py_result
        return _format_count_output(rows, total=total)
    except Exception as e:
        logging.warning("grep_search: ripgrep failed, fallback to Python: %s", e)
        if output_mode == "content":
            py_result = await _scan_content_python(search, rx, include, run_ctx)
            if py_result is None:
                return None
            return _format_content_output(py_result)
        if output_mode == "files_with_matches":
            py_result = await _scan_files_python(search, rx, include, run_ctx)
            if py_result is None:
                return None
            rows, total = py_result
            return _format_files_output(rows, total=total)
        py_result = await _scan_count_python(search, rx, include, run_ctx)
        if py_result is None:
            return None
        rows, total = py_result
        return _format_count_output(rows, total=total)


@register_tool(name="grep_search", toolset="filesystem")
class GrepSearchTool(BaseTool):
    @property
    def name(self) -> str:
        return "grep_search"

    @property
    def description(self) -> str:
        backend = "ripgrep (rg)" if rg_executable() else "built-in Python scanner"
        return f"""Fast content search tool for local projects of any type.

Backend: uses {backend} when available.

Usage:
- Searches file contents using regular expressions.
- `output_mode`: `content` (default, lines with numbers), `files_with_matches` (paths only), `count` (match count per file).
- Use `include` to filter files by pattern, for example: "*.js", "*.{{ts,tsx}}", "*.md".
- Results are limited to 100 entries per mode.
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for in file contents"
                },
                "path": {
                    "type": "string",
                    "description": "Optional absolute directory path to search in; defaults to agent workspace."
                },
                "include": {
                    "type": "string",
                    "description": "File glob to include (e.g. *.py, *.{ts,tsx})"
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Result format: matching lines, file paths only, or per-file match counts.",
                },
            },
            "required": ["pattern"],
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
        pattern: str,
        path: Optional[str] = None,
        include: Optional[str] = None,
        output_mode: str = "content",
    ) -> ToolResult:
        if not pattern:
            return ToolErrorResult("pattern is required")

        mode = (output_mode or "content").strip().lower()
        if mode not in ("content", "files_with_matches", "count"):
            return ToolErrorResult(f"invalid output_mode: {output_mode}")

        try:
            search = resolve_search_dir(path, agent_ctx.workspace_path or "")
            if not search.exists() or not search.is_dir():
                return ToolErrorResult(f"grep failed: directory does not exist: {search}")
        except ValueError as e:
            return ToolErrorResult(f"grep failed: {e}")
        except Exception as e:
            return ToolErrorResult(f"grep failed: {e}")

        try:
            rx = re.compile(pattern)
        except re.error as e:
            return ToolErrorResult(f"invalid regex: {e}")

        try:
            output = await _grep_execute(search, pattern, rx, include, mode, run_ctx)
            if output is None:
                return run_ctx.aborted_tool_result(self.name)
            return ToolSuccessResult(output)
        except Exception as e:
            return ToolErrorResult(f"grep failed: {e}")
