from __future__ import annotations
import json
import logging
import re
from typing import List
from app.infrastructure.llms import llm_factory
from app.repo_analysis.services.mr_experience.change_filter import ChangeFilter
from app.repo_analysis.services.mr_experience.models import ExperiencePattern, ExperienceStep, FileChange


PATTERN_PROMPT = """你是资深研发，请根据一次合入的需求描述与变更文件，总结可复用的开发经验。
要求：
1. 只关注与需求强相关的文件改动
2. 输出严格 JSON（不要 markdown 代码块），格式：
{"title":"简短标题","steps":[{"file":"相对路径","action":"应如何修改的一句话"}]}
3. steps 不超过 12 条；action 要具体可执行
"""


class PatternSummarizerError(RuntimeError):
    """LLM 经验总结失败（不回退规则文案）。"""


class PatternSummarizer:
    """调用 LLM 生成经验标题与步骤；失败必须抛错供任务记 failed。"""

    @staticmethod
    async def summarize(
        commit_message: str,
        files: List[FileChange],
        commit_sha: str,
    ) -> ExperiencePattern:
        payload = {
            "commit_message": (commit_message or "").strip(),
            "files": [
                {
                    "path": f.path,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "hint_action": ChangeFilter.status_action(f.status),
                }
                for f in files
            ],
        }
        user_question = json.dumps(payload, ensure_ascii=False)
        try:
            llm = llm_factory.create_model()
            stream, _usage = await llm.chat_stream(
                system_prompt="你擅长从历史合入沉淀开发模式，输出必须是合法 JSON。",
                user_prompt=PATTERN_PROMPT,
                user_question=user_question,
            )
            chunks: List[str] = []
            async for chunk in stream:
                chunks.append(chunk)
            raw = "".join(chunks).strip()
        except Exception as e:
            raise PatternSummarizerError(f"LLM 调用失败: {e}") from e

        if not raw or raw.startswith("llm error:") or "max retries exceeded" in raw:
            raise PatternSummarizerError(f"LLM 返回无效: {raw[:200]}")

        data = PatternSummarizer._parse_json(raw)
        title = str(data.get("title") or "").strip()
        if not title:
            raise PatternSummarizerError("LLM JSON 缺少 title")
        steps_raw = data.get("steps") or []
        if not isinstance(steps_raw, list) or not steps_raw:
            raise PatternSummarizerError("LLM JSON 缺少 steps")
        steps: List[ExperienceStep] = []
        for item in steps_raw:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file") or "").strip()
            action = str(item.get("action") or "").strip()
            if file_path and action:
                steps.append(ExperienceStep(file=file_path, action=action))
        if not steps:
            raise PatternSummarizerError("LLM steps 解析为空")
        return ExperiencePattern(
            title=title,
            steps=steps,
            source_commits=[commit_sha],
            commit_message=(commit_message or "").strip(),
        )

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.I | re.S).strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.I)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise PatternSummarizerError(f"无法解析 JSON: {text[:200]}")
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError as e:
                raise PatternSummarizerError(f"无法解析 JSON: {e}") from e
        if not isinstance(data, dict):
            raise PatternSummarizerError("JSON 根节点不是对象")
        return data
