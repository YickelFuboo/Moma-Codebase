"""related 关键词扩展：短中文/业务词 → 路径与符号别名，提升难例召回。"""
from __future__ import annotations
from typing import Dict, List, Sequence


class RelatedKeywordExpander:
    """把短中文或口语词展开为可 exact/path/向量命中的英文别名。"""

    ALIASES: Dict[str, List[str]] = {
        "记忆": ["memorys", "MemoryExtract", "memory_extract", "consolidation"],
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
    }

    NOISE_PATH_PREFIXES = (
        "website/",
        "node_modules/",
        "packaging/",
        "alembic/",
        "data/",
        "scripts/",
    )

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

        for raw in keywords or []:
            kw = str(raw or "").strip()
            if not kw:
                continue
            _add(kw)
            folded = kw.casefold()
            for alias_key, aliases in cls.ALIASES.items():
                if alias_key.casefold() == folded or alias_key in kw or kw in alias_key:
                    for a in aliases:
                        _add(a)
        return out

    @classmethod
    def is_noise_path(cls, file_path: str) -> bool:
        norm = (file_path or "").replace("\\", "/").lstrip("./").lower()
        if not norm:
            return True
        return any(norm.startswith(p) or f"/{p}" in f"/{norm}" for p in cls.NOISE_PATH_PREFIXES)
