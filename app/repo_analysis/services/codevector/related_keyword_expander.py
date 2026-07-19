"""related 关键词扩展：短中文/业务词 → 路径与符号别名，提升难例召回。"""
from __future__ import annotations
import re
from typing import Dict, List, Sequence, Set


class RelatedKeywordExpander:
    """把短中文或口语词展开为可 exact/path/向量命中的英文别名。"""

    ALIASES: Dict[str, List[str]] = {
        "记忆": ["memorys", "memory", "MemoryExtract", "memory_extract", "consolidation"],
        "鉴权": ["jwt_validator", "JWTValidator", "jwks", "jwt_middleware"],
        "认证": ["jwt_validator", "JWTValidator", "jwks"],
        "websocket": ["websocket", "websocket_endpoint"],
        "websocket 通道": ["websocket", "websocket_endpoint"],
        "通道": ["websocket", "websocket_endpoint"],
        "知识库": ["KBService", "kb_service"],
        "知识库服务": ["KBService", "kb_service"],
        "文档解析": ["DocParserService", "doc_parser_service", "DocParser"],
        "检索": ["retrieval", "Dealer", "rerank"],
        "会话": ["SessionManager", "create_session", "session_manager"],
        "memory": ["memorys", "MemoryExtract", "memory_extract", "consolidation"],
        "long-term memory": ["memorys", "MemoryExtract", "memory_extract"],
        "long term memory": ["memorys", "MemoryExtract", "memory_extract"],
        "extract prompt": ["MemoryExtract", "memory_extract"],
    }

    TOKEN_STOP: Set[str] = {
        "for",
        "the",
        "and",
        "with",
        "from",
        "into",
        "that",
        "this",
        "agent",
        "default",
        "prompt",
        "where",
        "what",
        "how",
        "find",
        "查找",
        "相关",
        "实现",
        "位置",
        "在哪",
        "哪里",
    }

    # 单独作检索词时噪声大；有更具体词时丢弃
    GENERIC_TOKENS: Set[str] = {
        "manager",
        "service",
        "base",
        "provider",
        "client",
        "handler",
        "message",
        "messages",
        "connection",
        "process",
        "common",
        "utils",
        "util",
        "core",
        "data",
        "realtime",
        "quote",
        "market",
        "channel",
    }

    NOISE_PATH_PREFIXES = (
        "website/",
        "node_modules/",
        "packaging/",
        "alembic/",
        "data/",
        "scripts/",
    )

    _TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}")

    @classmethod
    def expand(cls, keywords: Sequence[str]) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()

        def _add(token: str) -> None:
            t = (token or "").strip()
            if not t:
                return
            key = t.casefold()
            if key in seen:
                return
            seen.add(key)
            out.append(t)

        seeds = list(keywords or [])
        for raw in list(seeds):
            for tok in cls.core_tokens(str(raw or "")):
                if tok not in seeds:
                    seeds.append(tok)

        for raw in seeds:
            kw = str(raw or "").strip()
            if not kw:
                continue
            _add(kw)
            # 长句不做整句别名子串匹配，避免误扩
            if len(kw) > 40:
                continue
            folded = kw.casefold()
            if folded in cls.GENERIC_TOKENS:
                continue
            for alias_key, aliases in cls.ALIASES.items():
                ak = alias_key.casefold()
                if ak == folded or ak in folded or folded in ak:
                    for a in aliases:
                        _add(a)
        return out

    @classmethod
    def core_tokens(cls, text: str) -> List[str]:
        """从自然语言 query 抽可对齐路径/符号的核心词。"""
        out: List[str] = []
        seen: Set[str] = set()
        for m in cls._TOKEN_RE.finditer(text or ""):
            tok = m.group(0).strip("-_")
            if not tok:
                continue
            key = tok.casefold()
            if key in cls.TOKEN_STOP or key in seen:
                continue
            if len(tok) < 2:
                continue
            seen.add(key)
            out.append(tok)
            if len(out) >= 12:
                break
        specific = [t for t in out if t.casefold() not in cls.GENERIC_TOKENS]
        return specific if specific else out

    @classmethod
    def is_noise_path(cls, file_path: str) -> bool:
        norm = (file_path or "").replace("\\", "/").lstrip("./").lower()
        if not norm:
            return True
        return any(norm.startswith(p) or f"/{p}" in f"/{norm}" for p in cls.NOISE_PATH_PREFIXES)
