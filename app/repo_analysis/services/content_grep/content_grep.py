from __future__ import annotations
import os
import re
from typing import Dict, List, Optional, Sequence, Set
from app.repo_analysis.services.repo_path_ignore import RepoPathIgnore
from app.utils.common import normalize_path


class ContentGrepService:
    """仓内全文/标识符 grep：对标 Instant Grep，供 resolve 并联召回。"""

    MAX_FILES_SCANNED = 8000
    MAX_HITS = 40
    MAX_FILE_BYTES = 1_500_000
    MAX_TERM_LEN = 80
    MIN_TERM_LEN = 2

    @classmethod
    def search(
        cls,
        repo_root: str,
        terms: Sequence[str],
        *,
        extensions: Optional[Set[str]] = None,
        top_k: int = 10,
        builtin_dir_names: Optional[Set[str]] = None,
    ) -> List[Dict[str, object]]:
        root = os.path.abspath(os.path.normpath(repo_root or ""))
        if not root or not os.path.isdir(root):
            return []
        queries = cls._normalize_terms(terms)
        if not queries:
            return []
        ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or set())}
        ignorer = RepoPathIgnore.load(root, builtin_dir_names=builtin_dir_names)
        best: Dict[str, Dict[str, object]] = {}
        scanned = 0

        for parent, dirs, files in os.walk(root):
            ignorer.filter_walk_dirs(parent, dirs)
            for name in files:
                if scanned >= cls.MAX_FILES_SCANNED:
                    break
                abs_path = os.path.join(parent, name)
                rel = normalize_path(os.path.relpath(abs_path, root))
                if ignorer.should_ignore_file(rel):
                    continue
                if ext_set:
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in ext_set:
                        continue
                scanned += 1
                hit = cls._scan_file(abs_path, rel, queries)
                if not hit:
                    continue
                prev = best.get(rel)
                if prev is None or float(hit["score"]) > float(prev["score"]):
                    best[rel] = hit
            if scanned >= cls.MAX_FILES_SCANNED:
                break

        ranked = sorted(best.values(), key=lambda it: (-float(it["score"]), str(it["file_path"])))
        return ranked[: max(1, min(top_k, cls.MAX_HITS))]

    @classmethod
    def _normalize_terms(cls, terms: Sequence[str]) -> List[str]:
        out: List[str] = []
        seen: Set[str] = set()
        for raw in terms:
            t = " ".join(str(raw or "").split()).strip()
            if not t:
                continue
            if len(t) < cls.MIN_TERM_LEN or len(t) > cls.MAX_TERM_LEN:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
            if len(out) >= 12:
                break
        return out

    @classmethod
    def _scan_file(
        cls,
        abs_path: str,
        rel_path: str,
        terms: Sequence[str],
    ) -> Optional[Dict[str, object]]:
        try:
            size = os.path.getsize(abs_path)
        except OSError:
            return None
        if size <= 0 or size > cls.MAX_FILE_BYTES:
            return None
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            return None
        if not text:
            return None

        best_score = 0.0
        best_line = 0
        best_term = ""
        best_snippet = ""
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            for term in terms:
                score = cls._line_score(line, term)
                if score <= best_score:
                    continue
                best_score = score
                best_line = idx
                best_term = term
                best_snippet = line.strip()[:240]

        if best_score <= 0:
            # 路径 stem 弱命中
            stem = os.path.splitext(os.path.basename(rel_path))[0].lower()
            for term in terms:
                tl = term.lower()
                if len(tl) >= 3 and (tl == stem or tl in stem or stem in tl):
                    return {
                        "file_path": rel_path.replace("\\", "/"),
                        "score": 1.2,
                        "match_source": "grep",
                        "channel": "grep",
                        "start_line": 1,
                        "end_line": 1,
                        "grep_term": term,
                        "snippet": "",
                    }
            return None

        return {
            "file_path": rel_path.replace("\\", "/"),
            "score": best_score,
            "match_source": "grep",
            "channel": "grep",
            "start_line": best_line,
            "end_line": best_line,
            "grep_term": best_term,
            "snippet": best_snippet,
        }

    @classmethod
    def _line_score(cls, line: str, term: str) -> float:
        if not line or not term:
            return 0.0
        if term.isascii() and re.search(r"^[A-Za-z_][A-Za-z0-9_]*$", term):
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", line):
                return 2.8
            if term.lower() in line.lower():
                return 1.6
            return 0.0
        if term in line:
            return 2.4
        if term.lower() in line.lower():
            return 1.8
        return 0.0
