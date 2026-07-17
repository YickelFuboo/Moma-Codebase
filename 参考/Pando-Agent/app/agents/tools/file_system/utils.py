import difflib
import shutil
from pathlib import Path
from typing import List, Optional


_RG_PATH: Optional[str] = None


def rg_executable() -> Optional[str]:
    global _RG_PATH
    if _RG_PATH is None:
        _RG_PATH = shutil.which("rg") or ""
    return _RG_PATH or None


def resolve_search_dir(path: Optional[str], workspace_path: str) -> Path:
    if path:
        search = Path(path).expanduser()
        if not search.is_absolute():
            raise ValueError("path must be an absolute directory path")
        return search.resolve()
    ws = (workspace_path or "").strip()
    if ws:
        return Path(ws).expanduser().resolve()
    return Path.cwd().resolve()


def suggest_similar_paths(missing: Path, *, limit: int = 5) -> List[str]:
    name = missing.name
    parent = missing.parent
    if not parent.exists() or not parent.is_dir():
        return []

    names: List[str] = []
    try:
        for entry in parent.iterdir():
            if entry.is_file():
                names.append(entry.name)
    except OSError:
        return []

    if not names:
        return []

    picked = difflib.get_close_matches(name, names, n=limit, cutoff=0.5)
    if not picked:
        lower = name.lower()
        partial = [n for n in names if lower in n.lower() or n.lower() in lower]
        picked = partial[:limit]
    return [str(parent / n) for n in picked]


def format_not_found_message(requested: str, missing: Path) -> str:
    suggestions = suggest_similar_paths(missing)
    if not suggestions:
        return f"File not found: {requested}"
    lines = [f"File not found: {requested}", "Did you mean:"]
    lines.extend(f"  - {p}" for p in suggestions)
    return "\n".join(lines)
