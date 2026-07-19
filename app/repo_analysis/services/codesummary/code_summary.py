import re
import logging
from typing import List
from app.repo_analysis.services.codesummary.model import ContentType
from app.infrastructure.llms import llm_factory


FUNCTION_SUMMARY_PROMPT = """请基于如下函数定义，总结本函数主要功能。要求内容精准、简洁，150字以内，并便于后续用自然语言检索定位。格式要求如下：
功能：函数主要功能描述（用业务/领域词，如鉴权、记忆、会话，不要只复述代码标识符）
场景：什么需求下会改到这个函数
关键参数：主要函数参数描述
"""

CLASS_SUMMARY_PROMPT = """请基于如下类/结构体定义，总结本类/结构体主要功能。要求内容精准、简洁，200字以内，并便于后续用自然语言检索定位。格式要求如下：
功能：类主要功能描述（用业务/领域词）
场景：什么需求下会改到这个类
关键属性：主要的类属性字段说明
关键方法：主要的类方法说明
"""

STRUCT_SUMMARY_PROMPT = """请基于如下结构体定义，总结本结构体主要功能。要求内容精准、简洁，200字以内，并便于后续用自然语言检索定位。格式要求如下：
功能：结构体主要功能描述（用业务/领域词）
场景：什么需求下会改到这个结构体
关键属性：主要的结构体属性字段说明
关键方法：主要的结构体方法说明
"""

INTERFACE_SUMMARY_PROMPT = """请基于如下接口定义，总结本接口主要功能。要求内容精准、简洁，200字以内，并便于后续用自然语言检索定位。格式要求如下：
功能：接口主要功能描述（用业务/领域词）
场景：什么需求下会改到这个接口
关键方法：主要的接口方法说明
"""

FILE_SUMMARY_PROMPT = """请基于如下源码文件内容，总结本代码文件的主要功能。要求内容精准、简洁，150字以内，并便于后续用自然语言检索定位。格式要求如下：
功能：文件主要功能描述（用业务/领域词，如鉴权、记忆、消息通道）
场景：什么需求下会改到这个文件
"""

FOLDER_SUMMARY_PROMPT = """请基于如下文件夹（模块）中子文件夹和子文件功能描述。总结本文件夹（模块）主要功能，要求内容精准、简洁，150字以内，并便于后续用自然语言检索定位。格式要求如下：
功能：文件夹（模块）主要功能描述（用业务/领域词）
场景：什么需求下会改到这个模块
"""

_DOCSTRING_RE = re.compile(
    r'^\s*(?:[ruRU]{0,2})("""|\'\'\')(.*?)\1',
    re.DOTALL,
)
_SIG_RE = re.compile(
    r"^\s*(?:(?:async\s+)?def|class|func|interface|struct|type)\s+[^\n{;]+",
    re.MULTILINE,
)


def _is_stream_error_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t.startswith("llm error:"):
        return True
    if t.startswith("Invalid response"):
        return True
    if "Unexpected error: max retries exceeded" in t:
        return True
    return False


def _strip_think_tags(text: str) -> str:
    if not text:
        return ""
    pattern = r"<\s*think\s*>.*?<\s*/\s*think\s*>"
    return re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL).strip()


class CodeSummary:
    """符号/文件摘要：优先 LLM，失败时确定性回退以保证可嵌入检索。"""

    @staticmethod
    def fallback_summary(content: str, content_type: ContentType) -> str:
        """LLM 不可用时的确定性摘要：签名 + docstring + 源码预览。"""
        src = (content or "").strip()
        if not src:
            return ""
        kind_label = {
            ContentType.FILE: "文件",
            ContentType.CLASS: "类",
            ContentType.STRUCT: "结构体",
            ContentType.INTERFACE: "接口",
            ContentType.FUNCTION: "函数",
            ContentType.FOLDER: "模块",
            ContentType.CODE_CHUNK: "代码块",
        }.get(content_type, "符号")

        sig = ""
        m_sig = _SIG_RE.search(src)
        if m_sig:
            sig = " ".join(m_sig.group(0).split())[:200]

        doc = ""
        # 常见：签名后紧跟 docstring
        after_sig = src[m_sig.end() :] if m_sig else src
        m_doc = _DOCSTRING_RE.search(after_sig[:1200])
        if m_doc:
            doc = " ".join(m_doc.group(2).strip().split())[:180]
        if not doc:
            for ln in src.splitlines()[:12]:
                s = ln.strip()
                if s.startswith("#") and len(s) > 2:
                    doc = s.lstrip("#").strip()[:180]
                    break
                if s.startswith("//") and len(s) > 3:
                    doc = s[2:].strip()[:180]
                    break

        lines = [ln.strip() for ln in src.splitlines() if ln.strip()]
        preview = " ".join(lines[:4])[:240]

        parts = [f"功能：{kind_label}摘要（回退）"]
        if doc:
            parts[0] = f"功能：{doc}"
        if sig:
            parts.append(f"签名：{sig}")
        parts.append(f"场景：检索定位相关实现时可能命中")
        if preview and not doc:
            parts.append(f"预览：{preview}")
        return "\n".join(parts)

    @staticmethod
    async def llm_summarize(content: str, content_type: ContentType) -> str:
        """使用 LLM 生成代码内容摘要；失败则确定性回退。"""
        fallback = CodeSummary.fallback_summary(content, content_type)
        try:
            system_prompt = (
                "你是一个代码分析专家，擅长把符号功能总结成便于检索的业务描述："
                "优先使用领域词（鉴权/JWT/记忆/会话/流式/工具调用等），"
                "避免只堆砌标识符；摘要要能支撑「用自然语言找该改哪个文件」。"
            )

            if content_type == ContentType.FILE:
                user_prompt = FILE_SUMMARY_PROMPT
            elif content_type == ContentType.CLASS:
                user_prompt = CLASS_SUMMARY_PROMPT
            elif content_type == ContentType.FUNCTION:
                user_prompt = FUNCTION_SUMMARY_PROMPT
            elif content_type == ContentType.STRUCT:
                user_prompt = STRUCT_SUMMARY_PROMPT
            elif content_type == ContentType.INTERFACE:
                user_prompt = INTERFACE_SUMMARY_PROMPT
            elif content_type == ContentType.FOLDER:
                user_prompt = FOLDER_SUMMARY_PROMPT
            else:
                return fallback

            llm = llm_factory.create_model()
            stream, _usage = await llm.chat_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                user_question=content,
            )
            chunks: List[str] = []
            async for chunk in stream:
                chunks.append(chunk)
            full = "".join(chunks)
            if _is_stream_error_text(full):
                return fallback

            result = _strip_think_tags(full).strip()
            return result or fallback

        except Exception as e:
            logging.error("生成%s摘要失败，使用回退: %s", content_type, e)
            return fallback
