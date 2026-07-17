import asyncio
import os
import re
import sys
from pathlib import Path

DENY_PATTERNS_LINUX = [
    r"\brm\s+-[rf]{1,2}\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"(?:^|[;&|]\s*)format\b",
    r"\b(mkfs|diskpart)\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\b(shutdown|reboot|poweroff)\b",
    r":\(\)\s*\{.*\};\s*:",
]

DENY_PATTERNS_WIN = [
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s",
    r"\bformat\b",
    r"\bdiskpart\b",
    r"\b(shutdown|reboot)\b",
]

FOREGROUND_BACKGROUND_PATTERNS = [
    r"&\s*$",
    r"\bnohup\b",
    r"\bdisown\b",
    r"\bstart\s+/b\b",
]

MAX_OUTPUT_CHARS = 10000
MAX_BACKGROUND_STREAM_CHARS = 1_000_000


def default_deny_patterns() -> list[str]:
    return DENY_PATTERNS_WIN if sys.platform == "win32" else DENY_PATTERNS_LINUX


def resolve_working_dir(working_dir: str | None, workspace_path: str | None) -> str:
    if working_dir:
        return working_dir
    ws = (workspace_path or "").strip()
    if ws:
        return ws
    return os.getcwd()


def _path_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return path.resolve() == root.resolve()


def guard_command(
    command: str,
    cwd: str,
    *,
    deny_patterns: list[str],
    allow_patterns: list[str],
    restrict_to_workspace: bool,
    workspace_root: str | None = None,
    background: bool = False,
) -> str | None:
    cmd = command.strip()
    lower = cmd.lower()

    for pattern in deny_patterns:
        if re.search(pattern, lower):
            return "Error: Command blocked by safety guard (dangerous pattern detected)"

    if not background:
        for pattern in FOREGROUND_BACKGROUND_PATTERNS:
            if re.search(pattern, lower):
                return (
                    "Error: Use shell_exec(background=true) for background tasks; "
                    "do not use shell-level &, nohup, disown, or start /b"
                )

    if allow_patterns and not any(re.search(p, lower) for p in allow_patterns):
        return "Error: Command blocked by safety guard (not in allowlist)"

    if restrict_to_workspace:
        if "..\\" in cmd or "../" in cmd:
            return "Error: Command blocked by safety guard (path traversal detected)"

        root_path = None
        if workspace_root:
            try:
                root_path = Path(workspace_root).expanduser().resolve()
            except Exception:
                return "Error: Command blocked by safety guard (invalid workspace root)"

        try:
            cwd_path = Path(cwd).expanduser().resolve()
        except Exception:
            return "Error: Command blocked by safety guard (invalid working directory)"

        if root_path is not None and not _path_within_root(cwd_path, root_path):
            return "Error: Command blocked by safety guard (working dir outside workspace)"

        check_root = root_path or cwd_path
        win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
        posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)
        for raw in win_paths + posix_paths:
            try:
                p = Path(raw.strip()).expanduser().resolve()
            except Exception:
                continue
            if p.is_absolute() and not _path_within_root(p, check_root):
                return "Error: Command blocked by safety guard (path outside workspace)"

    return None


async def create_command_process(command: str, cwd: str) -> asyncio.subprocess.Process:
    popen_kwargs: dict = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }

    if sys.platform == "win32":
        return await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
            cwd=cwd,
            **popen_kwargs,
        )
    return await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        **popen_kwargs,
    )


def truncate_output(text: str, max_len: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n... (truncated, {len(text) - max_len} more chars)"
