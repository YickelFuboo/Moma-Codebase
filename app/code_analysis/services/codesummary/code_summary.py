import re
import logging
from typing import List
from app.code_analysis.services.codesummary.model import ContentType
from app.infrastructure.llms import llm_factory


FUNCTION_SUMMARY_PROMPT = """请基于如下函数定义，总结本函数主要功能。要求内容精准、简洁，150字以内。格式要求如下：
功能：函数主要功能描述
关键参数：主要函数参数描述
"""

CLASS_SUMMARY_PROMPT = """请基于如下类/结构体定义，总结本类/结构体主要功能。要求内容精准、简洁，200字以内。格式要求如下：
功能：类主要功能描述
关键属性：主要的类属性字段说明
关键方法：主要的类方法说明
"""

STRUCT_SUMMARY_PROMPT = """请基于如下结构体定义，总结本结构体主要功能。要求内容精准、简洁，200字以内。格式要求如下：
功能：结构体主要功能描述
关键属性：主要的结构体属性字段说明
关键方法：主要的结构体方法说明
"""

INTERFACE_SUMMARY_PROMPT = """请基于如下接口定义，总结本接口主要功能。要求内容精准、简洁，200字以内。格式要求如下：
功能：接口主要功能描述
关键方法：主要的接口方法说明
"""

FILE_SUMMARY_PROMPT = """请基于如下源码文件内容，总结本代码文件的主要功能。要求内容精准、简洁，150字以内。格式要求如下：
功能：文件主要功能描述
"""

FOLDER_SUMMARY_PROMPT = """请基于如下文件夹（模块）中子文件夹和子文件功能描述。总结本文件夹（模块）主要功能，要求内容精准、简洁，150字以内。格式要求如下：
功能：文件夹（模块）主要功能描述
"""


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
    return re.sub(pattern,"",text,flags=re.IGNORECASE|re.DOTALL).strip()


class CodeSummary:

    @staticmethod
    async def llm_summarize(content: str, content_type: ContentType) -> str:
        """使用LLM生成代码内容摘要
        
        Args:
            content: 代码内容
            content_type: 内容类型（文件/类/函数）
            
        Returns:
            str: 生成的摘要
        """
        try:
            system_prompt = "你是一个代码分析专家，在许多编程语言、框架、设计模式和最佳实践方面拥有广泛的知识，擅长总结代码的核心功能，便于后续在开发中快速定位到需修改的文件。"

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
                return ""

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
                return ""

            # 过滤掉模型结果中的think内容
            result = _strip_think_tags(full).strip()
            return result
        
        except Exception as e:
            logging.error(f"生成{content_type}摘要失败: {e}")
            return ""