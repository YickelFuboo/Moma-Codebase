from __future__ import annotations
from typing import Dict, List, Optional


class ResolveResultPresenter:
    """把融合命中整理成 Agent 可读的 why / summary / TopN。"""

    AGENT_ITEM_LIMIT = 3

    _SOURCE_HINT = {
        "exact": "精确命中",
        "grep": "全文/标识符命中",
        "symbol_summary": "符号摘要相关",
        "line_chunk": "相似代码块",
        "codegraph": "图谱关系",
        "mr_experience": "历史经验",
        "api": "公开接口",
    }

    @classmethod
    def why_for(cls, item: Dict[str, object]) -> str:
        channel = str(item.get("channel") or "")
        source = str(item.get("match_source") or "")
        hint = cls._SOURCE_HINT.get(source) or source or channel or "命中"
        if item.get("fallback"):
            hint = f"弱相关兜底·{hint}"
        fp = str(item.get("file_path") or "").strip()
        symbol = str(item.get("symbol_name") or "").strip()
        title = str(item.get("title") or item.get("pattern_title") or "").strip()
        relation = str(item.get("graph_relation") or "").strip()
        target = str(item.get("graph_target") or "").strip()

        if relation and fp:
            focus = f"{relation} → {fp}"
            if target:
                focus = f"{relation}({target}) → {fp}"
        elif symbol and fp:
            focus = f"{fp}#{symbol}"
        elif fp:
            focus = fp
        elif title:
            focus = title
        elif symbol:
            focus = symbol
        else:
            focus = "未定位到路径"
        return f"[{channel or source}] {hint}：{focus}"

    @classmethod
    def annotate(cls, items: List[Dict[str, object]]) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        for it in items:
            row = dict(it)
            row["why"] = cls.why_for(row)
            out.append(row)
        return out

    @classmethod
    def agent_items(cls, items: List[Dict[str, object]]) -> List[Dict[str, object]]:
        """对外最多 Top3；精确命中优先；若有兜底条，强制占 1 席。"""
        limit = cls.AGENT_ITEM_LIMIT
        if not items:
            return []

        def _key(it: Dict[str, object]) -> str:
            fp = str(it.get("file_path") or "")
            if fp:
                return f"file:{fp}"
            title = str(it.get("title") or "")
            if title:
                return f"title:{title}"
            return str(it.get("symbol_name") or id(it))

        def _prefer(it: Dict[str, object]) -> tuple:
            source = str(it.get("match_source") or "")
            tier = str(it.get("exact_tier") or "")
            score = float(it.get("score") or it.get("quality_score") or it.get("similarity") or 0)
            if source == "exact" and tier == "symbol":
                band = 0
            elif source == "exact":
                band = 1
            elif source == "grep" and score >= 2.5:
                band = 2
            elif source == "symbol_summary":
                band = 3
            elif source in {"codegraph", "graph"}:
                band = 4
            elif source == "grep":
                band = 5
            elif source == "line_chunk":
                band = 6
            else:
                band = 7
            return (band, -score)

        ordered = sorted(items, key=_prefer)
        fallback = next((it for it in ordered if it.get("fallback")), None)
        if fallback is None:
            return list(ordered[:limit])

        primary: List[Dict[str, object]] = []
        seen = {_key(fallback)}
        for it in ordered:
            if it.get("fallback"):
                continue
            k = _key(it)
            if k in seen:
                continue
            seen.add(k)
            primary.append(it)
            if len(primary) >= max(0, limit - 1):
                break
        return primary + [fallback]

    @classmethod
    def summary(
        cls,
        *,
        intent: str,
        items: List[Dict[str, object]],
        fused_total: int,
        fallback_used: Optional[str],
    ) -> str:
        if not items:
            base = f"{intent} 未命中可用结果"
            if fallback_used:
                return f"{base}（已尝试 {fallback_used} 兜底仍空）"
            return base
        top = items[0]
        top_focus = str(top.get("file_path") or top.get("title") or top.get("symbol_name") or "?")
        symbol = str(top.get("symbol_name") or "").strip()
        if symbol and top.get("file_path"):
            top_focus = f"{top.get('file_path')}#{symbol}"
        parts = [
            f"{intent} 推荐 {len(items)} 条（融合池 {fused_total}）",
            f"优先看 {top_focus}",
        ]
        if fallback_used:
            parts.append(f"已附带 {fallback_used} 兜底")
        return "；".join(parts)
