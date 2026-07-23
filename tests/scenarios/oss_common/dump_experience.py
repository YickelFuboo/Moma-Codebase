"""导出已 ready 的 MR 经验（全量，便于人工检视）。"""
from __future__ import annotations
import asyncio
import json
from sqlalchemy import select
from app.infrastructure.database import get_db_session
from app.repo_analysis.models.experience_status import ExperienceItemStatus, MrExperienceItem
from app.runtime import init_runtime, release_runtime
from tests.scenarios.oss_common.eval_output import ScenarioOutputDir


REPOS = [
    ("go", "99b77fa8-c711-4f43-b566-d49da6a4da38", r"F:\开源项目\go"),
    ("django", "f6a8d600-eb2e-4d0f-b877-dc2acf2caf61", r"F:\开源项目\django"),
]


async def dump() -> None:
    await init_runtime()
    out: dict = {}
    try:
        async with get_db_session() as db:
            for name, rid, path in REPOS:
                items = (
                    await db.execute(
                        select(MrExperienceItem)
                        .where(
                            MrExperienceItem.repo_id == rid,
                            MrExperienceItem.status == ExperienceItemStatus.READY.value,
                        )
                        .order_by(MrExperienceItem.committed_at.desc().nullslast())
                    )
                ).scalars().all()
                rows = []
                pattern_count = 0
                for it in items:
                    try:
                        payload = json.loads(it.steps_json or "{}")
                    except json.JSONDecodeError:
                        payload = {}
                    patterns = payload.get("patterns") or []
                    if not isinstance(patterns, list):
                        patterns = []
                    pattern_count += len(patterns)
                    rows.append(
                        {
                            "commit_sha": it.commit_sha,
                            "commit_message": it.commit_message,
                            "committed_at": it.committed_at.isoformat() if it.committed_at else None,
                            "is_merge": bool(it.is_merge),
                            "title": it.title,
                            "kept_after_quality_filter": payload.get("kept_after_quality_filter"),
                            "total_extracted": payload.get("total_extracted"),
                            "patterns": patterns,
                        }
                    )
                out[name] = {
                    "path": path,
                    "repo_id": rid,
                    "ready_mrs": len(rows),
                    "pattern_count": pattern_count,
                    "items": rows,
                }
    finally:
        await release_runtime()

    json_path = ScenarioOutputDir.path(".tmp_oss_experience_dump.json")
    md_path = ScenarioOutputDir.path(".tmp_oss_experience_dump.md")
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Go / Django MR 经验全量导出", ""]
    for name in ("go", "django"):
        block = out[name]
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"- path: `{block['path']}`")
        lines.append(f"- ready MR: **{block['ready_mrs']}**")
        lines.append(f"- 经验条数: **{block['pattern_count']}**")
        lines.append("")
        for i, item in enumerate(block["items"], 1):
            lines.append(f"### {i}. {item.get('title') or '(无标题)'}")
            lines.append("")
            sha = (item.get("commit_sha") or "")[:12]
            lines.append(f"- commit: `{sha}`")
            lines.append(f"- message: {item.get('commit_message') or ''}")
            lines.append(f"- committed_at: {item.get('committed_at') or ''}")
            lines.append("")
            for j, p in enumerate(item.get("patterns") or [], 1):
                lines.append(f"#### 经验 {j}: {p.get('title') or ''}")
                lines.append("")
                lines.append(f"- scenario: {p.get('scenario') or ''}")
                lines.append(f"- quality: {p.get('quality_score')}")
                pats = p.get("patterns") or []
                if pats:
                    lines.append("- patterns:")
                    for x in pats:
                        lines.append(f"  - {x}")
                plan = p.get("plan") or []
                if plan:
                    lines.append("- plan:")
                    for x in plan:
                        lines.append(f"  - {x}")
                anchors = p.get("anchors") or []
                if anchors:
                    lines.append(f"- anchors: {', '.join(str(a) for a in anchors)}")
                files = p.get("relevant_files") or []
                if files:
                    lines.append("- relevant_files:")
                    for x in files[:20]:
                        lines.append(f"  - `{x}`")
                lines.append("")
            lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"JSON={json_path.resolve()}")
    print(f"MD={md_path.resolve()}")
    for name in ("go", "django"):
        print(f"{name} ready_mrs={out[name]['ready_mrs']} patterns={out[name]['pattern_count']}")


if __name__ == "__main__":
    asyncio.run(dump())
