"""
工具输出截断：超长结果不塞入模型上下文，完整内容落盘到 workspace/tool_output。
仅摘要进上下文，metadata 供人/UI 使用。
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Literal, Optional
from app.config.settings import settings


class TruncateResult:
    """截断结果：未超限时 content 为原文；超限时为摘要 + hint，并落盘完整内容。"""
    __slots__ = ("content", "truncated", "output_path")

    def __init__(
        self,
        content: str,
        truncated: bool,
        output_path: Optional[str] = None,
    ):
        self.content = content
        self.truncated = truncated
        self.output_path = output_path


class Truncate:
    """工具输出截断：超长落盘、仅摘要进上下文，常量与入口集中在此类。"""
    SUB_DIR = "tool_output"
    RETENTION_DAYS = 7

    @staticmethod
    def _tool_output_dir(workspace_path: str) -> Path:
        """workspace/tool_output 目录，不存在则创建。"""
        root = Path(workspace_path).expanduser().resolve()
        out = root / Truncate.SUB_DIR
        out.mkdir(parents=True, exist_ok=True)
        return out

    @staticmethod
    def _ascending_id() -> str:
        """生成唯一 id：tool_<timestamp_hex>_<random>，便于按时间清理。"""
        ts = int(time.time() * 1000)
        rnd = secrets.token_hex(6)
        return f"tool_{ts:014x}_{rnd}"

    @staticmethod
    def _file_id_timestamp(file_id: str) -> int:
        """从 tool_<hex>_<random> 解析时间戳（毫秒）。"""
        parts = file_id.split("_")
        if len(parts) < 2:
            return 0
        try:
            return int(parts[1], 16)
        except ValueError:
            return 0

    @staticmethod
    def output(
        text: str,
        workspace_path: str,
        *,
        max_lines: int = settings.tool_result_truncate_max_lines,
        max_bytes: int = settings.tool_result_truncate_max_bytes,
        direction: Literal["head", "tail"] = "head",
        has_task_tool: bool = False,
    ) -> TruncateResult:
        """
        若 text 未超限则原样返回；超限则截取 preview，完整内容写入 workspace/tool_output/<id>，
        返回摘要（preview + 截断说明 + hint），且 truncated=True、output_path 指向落盘文件。
        发给模型的仅为 content（摘要），不读 output_path；metadata 中的 truncated/outputPath 供人/UI 用。
        """
        if not text:
            return TruncateResult(content=text, truncated=False)
        lines = text.split("\n")
        total_bytes = len(text.encode("utf-8"))
        if len(lines) <= max_lines and total_bytes <= max_bytes:
            return TruncateResult(content=text, truncated=False)

        out: list[str] = []
        bytes_so_far = 0
        hit_bytes = False

        if direction == "head":
            for i in range(min(len(lines), max_lines)):
                line = lines[i]
                line_size = len(line.encode("utf-8")) + (1 if i > 0 else 0)
                if bytes_so_far + line_size > max_bytes:
                    hit_bytes = True
                    break
                out.append(line)
                bytes_so_far += line_size
        else:
            for i in range(len(lines) - 1, -1, -1):
                if len(out) >= max_lines:
                    break
                line = lines[i]
                line_size = len(line.encode("utf-8")) + (1 if out else 0)
                if bytes_so_far + line_size > max_bytes:
                    hit_bytes = True
                    break
                out.insert(0, line)
                bytes_so_far += line_size

        removed = total_bytes - bytes_so_far if hit_bytes else len(lines) - len(out)
        unit = "bytes" if hit_bytes else "lines"
        preview = "\n".join(out)

        out_dir = Truncate._tool_output_dir(workspace_path)
        file_id = Truncate._ascending_id()
        filepath = out_dir / file_id
        filepath.write_text(text, encoding="utf-8")
        output_path = str(filepath)

        if has_task_tool:
            hint = (
                f"The tool call succeeded but the output was truncated. Full output saved to: {output_path}\n"
                "Use the spawn tool to have subagent read or process this file. "
                "Do NOT read the full file yourself - delegate to subagent."
            )
        else:
            hint = (
                f"The tool call succeeded but the output was truncated. Full output saved to: {output_path}\n"
                "Use Grep to search the full content or Read with offset/limit to view specific sections."
            )
        if direction == "head":
            message = f"{preview}\n\n...{removed} {unit} truncated...\n\n{hint}"
        else:
            message = f"...{removed} {unit} truncated...\n\n{hint}\n\n{preview}"

        return TruncateResult(content=message, truncated=True, output_path=output_path)

    @staticmethod
    def cleanup_old_outputs(
        workspace_path: str,
        retention_days: int = RETENTION_DAYS,
    ) -> int:
        """
        删除 workspace/tool_output 下超过 retention_days 天的文件。可由定时任务调用。
        返回删除的文件数量。
        """
        out_dir = Truncate._tool_output_dir(workspace_path)
        cutoff_ms = int((time.time() - retention_days * 86400) * 1000)
        removed = 0
        for p in out_dir.iterdir():
            if not p.is_file() or not p.name.startswith("tool_"):
                continue
            ts = Truncate._file_id_timestamp(p.name)
            if ts > 0 and ts < cutoff_ms:
                try:
                    p.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed
