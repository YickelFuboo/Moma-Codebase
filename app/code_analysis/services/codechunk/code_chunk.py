import os
import re
from dataclasses import dataclass
from typing import List, Optional
from app.config.settings import settings


_TRIVIAL_PY_ACCESSOR = re.compile(
    r"(?ms)^\s*@\s*property\b.*|^\s*def\s+(get|set)[A-Za-z0-9_]+\s*\([^)]*\)\s*:\s*(?:\r?\n\s*(?:return\s+|pass\s*$|raise\s+NotImplementedError))?",
)
_TRIVIAL_ONE_LINE_GETTER = re.compile(
    r"^\s*def\s+(get|set)[A-Za-z0-9_]+\s*\([^)]*\)\s*:\s*return\s+.+$",
)
_TRIVIAL_JAVA_GO_CPP_SETTER_GETTER = re.compile(
    r"(?ms)^\s*(public|private|protected)?\s*(static\s+)?[\w<>\[\]]+\s+(get|set)[A-Za-z0-9_]*\s*\([^)]*\)\s*\{\s*(return\s+[^;]+;|this\.[A-Za-z0-9_]+\s*=\s*[A-Za-z0-9_]+;)\s*\}\s*$"
)
_TRIVIAL_SINGLE_LINE_RETURN = re.compile(
    r"(?ms)^\s*(return\s+[^;]+;|return\s+.+)$"
)
_LOW_VALUE_HEADER_BLOCK = re.compile(
    r"(?ms)^\s*((package\s+[\w\.]+;|import\s+[\w\.\*]+;|using\s+namespace\s+\w+\s*;|#include\s+[<\"].+[>\"]|module\s+\w+).*)$"
)


TARGET_LINES = settings.code_analysis_line_chunk_target_lines or 5
OVERLAP_LINES = settings.code_analysis_line_chunk_overlap_lines or 1
MAX_CHUNK_LINES = settings.code_analysis_line_chunk_max_lines or 200


@dataclass(frozen=True)
class LineTextChunk:
    """单行切片结果：在源文件中的起止行号与片段文本。"""
    start_line: int
    end_line: int
    text: str


class CodeChunkService:
    """源码行级切片：按配置将文件拆成若干带行号范围的文本块，供向量化使用。"""

    @staticmethod
    def slice_file(abs_path: str, source_text: Optional[str] = None) -> List[LineTextChunk]:
        """对单个源文件按配置做行切片，返回有序片段列表。
        若传入 source_text（例如与 AST 分析共用同一次读盘结果），则不再读取文件。
        """
        if source_text is not None:
            text = source_text
        else:
            text = CodeChunkService._read_source_file(abs_path)
        ext = os.path.splitext(abs_path)[1].lower()
        # 切片源代码
        return CodeChunkService._slice_source_text(text, file_ext=ext)
    
    @staticmethod
    def _read_source_file(abs_path: str) -> str:
        """从磁盘读取源码全文（UTF-8，非法字节忽略）。"""
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    @staticmethod
    def _slice_source_text(text: str, *, file_ext: str = ".py") -> List[LineTextChunk]:
        """按配置的目标行数、重叠与最大块长，将整段文本切成 LineTextChunk；会扩展边界以避免截断括号与 Python 块结构。"""
        if not text.strip():
            return []

        target_lines = TARGET_LINES
        overlap_lines = OVERLAP_LINES
        overlap_lines = (
            max(target_lines // 2, 1) if target_lines > 1 else 0
        ) if overlap_lines >= target_lines else overlap_lines

        lines = text.splitlines()
        n = len(lines)
        if n == 0:
            return []
        out: List[LineTextChunk] = []
        start = 0
        while start < n:
            raw_end = min(start + target_lines, n)
            end = CodeChunkService._extend_chunk_end(lines, start, raw_end, start + MAX_CHUNK_LINES, file_ext, MAX_CHUNK_LINES)
            chunk_text = "\n".join(lines[start:end]).strip()
            if chunk_text and not CodeChunkService._should_drop_chunk(chunk_text, file_ext):
                out.append(LineTextChunk(start + 1, end, chunk_text))
            if end >= n:
                break
            step = end - overlap_lines if overlap_lines > 0 else end
            start = max(step, start + 1)
        return out

    @staticmethod
    def _extend_chunk_end(
        lines: List[str],
        start: int,
        raw_end: int,
        max_end: int,
        file_ext: str,
        max_extend_steps: int,
    ) -> int:
        """在初步结束行基础上向后扩展，直到行续接、括号平衡、Python 冒号块体被包含或达到上限。"""
        max_end = min(len(lines), max_end)
        end = min(max(raw_end, start + 1), len(lines))

        guard = 0
        while end < max_end and guard < max_extend_steps:
            guard += 1
            if CodeChunkService._line_continues(lines[end - 1]):
                end += 1
                continue
            joined = "\n".join(lines[start:end])
            if CodeChunkService._delimiter_unbalanced(joined):
                end += 1
                continue
            if file_ext == ".py":
                new_end = CodeChunkService._extend_python_after_colon(lines, end, max_end)
                if new_end > end:
                    end = new_end
                    continue
            break
        return end

    @staticmethod
    def _line_continues(line: str) -> bool:
        """判断该行是否以反斜杠结尾（行继续），注释行不计。"""
        s = line.rstrip("\n")
        if not s.strip() or s.lstrip().startswith("#"):
            return False
        return s.endswith("\\")

    @staticmethod
    def _extend_python_after_colon(lines: List[str], end: int, max_end: int) -> int:
        """若切片最后一行以冒号结尾，则扩展以包含缩进大于该行的首个语句块（至去缩进或上限）。"""
        if end < 1 or end > len(lines):
            return end
        colon_line = lines[end - 1]
        if not colon_line.rstrip().endswith(":"):
            return end
        colon_ind = CodeChunkService._indent_len(colon_line)
        i = end
        while i < max_end and i < len(lines):
            s = lines[i]
            if not s.strip():
                i += 1
                continue
            if s.lstrip().startswith("#"):
                i += 1
                continue
            ind = CodeChunkService._indent_len(s)
            if ind > colon_ind:
                i += 1
                continue
            break
        return i

    @staticmethod
    def _indent_len(line: str) -> int:
        """计算行首空格与制表符宽度（用于 Python 缩进比较）。"""
        return len(line) - len(line.lstrip(" \t"))

    @staticmethod
    def _delimiter_unbalanced(text: str) -> bool:
        """判断括号/方括号/花括号在简单字符串扫描下是否未配对闭合；为 True 时应继续向下扩行。"""
        stack: List[str] = []
        in_str: Optional[str] = None
        escape = False
        i = 0
        while i < len(text):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == in_str:
                    in_str = None
                i += 1
                continue
            if ch in ("\"", "'"):
                in_str = ch
                i += 1
                continue
            if ch == "(":
                stack.append(")")
            elif ch == "[":
                stack.append("]")
            elif ch == "{":
                stack.append("}")
            elif ch in ")]}":
                if stack and stack[-1] == ch:
                    stack.pop()
                else:
                    return False
            i += 1
        return len(stack) > 0

    @staticmethod
    def _should_drop_chunk(chunk_text: str, file_ext: str) -> bool:
        """按语言启发式过滤低价值切片，避免无效上下文进入向量库。

        当前会过滤的内容：
        1) 通用（所有语言）：
           - 空白片段；
           - 仅由 package/import/include/using/module 等头部声明组成，且总行数较短（<=5）的片段。
        2) Python：
           - 过短的一行 getter/setter；
           - 过短且匹配 @property/get*/set* 模式的访问器片段；
           - 仅包含超短 return 的片段（<=3 行）。
        3) Java/Go/C/C++（含 .h/.hpp）：
           - 过短且模式化的 getter/setter 函数体；
           - 仅包含超短 return 的片段（<=3 行）；
           - 只包含结构噪音符号（如 { } / };）的片段。

        目的：优先保留在后续检索/开发中更有参考价值的业务逻辑代码块。
        """
        lines = [ln for ln in chunk_text.splitlines() if ln.strip()]
        if not lines:
            return True
        if len(lines) <= 5 and _LOW_VALUE_HEADER_BLOCK.search(chunk_text):
            return True

        if file_ext == ".py":
            if len(lines) <= 4 and _TRIVIAL_ONE_LINE_GETTER.search(chunk_text):
                return True
            if len(lines) <= 8 and _TRIVIAL_PY_ACCESSOR.search(chunk_text):
                return True
            if len(lines) <= 3 and _TRIVIAL_SINGLE_LINE_RETURN.search(chunk_text):
                return True
            return False

        if file_ext in {".java", ".go", ".cpp", ".c", ".h", ".hpp"}:
            if len(lines) <= 7 and _TRIVIAL_JAVA_GO_CPP_SETTER_GETTER.search(chunk_text):
                return True
            if len(lines) <= 3 and _TRIVIAL_SINGLE_LINE_RETURN.search(chunk_text):
                return True
            stripped = [ln.strip() for ln in lines]
            if len(stripped) <= 3 and all(it in {"{", "}", "};"} for it in stripped):
                return True
        return False

