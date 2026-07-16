import logging
from typing import List
from app.infrastructure.llms import llm_factory
from app.lib_analysis.schemes.public_api import PublicApi


API_SUMMARY_PROMPT = """请基于如下公开接口定义，总结该接口的功能与参数。要求内容精准、简洁，200字以内。格式要求如下：
功能：接口主要功能描述
关键参数：主要参数含义与约束
返回：返回值含义（若无则写无）
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


class ApiSummaryService:
    """对 Lib 公开接口生成功能/参数摘要。"""

    @staticmethod
    async def summarize(api: PublicApi) -> str:
        content = ApiSummaryService._build_llm_input(api)
        try:
            llm = llm_factory.create_model()
            stream, _usage = await llm.chat_stream(
                system_prompt=(
                    "你是一个库接口文档专家，擅长把公开 API 的功能与参数说明写清楚，"
                    "便于编码 Agent 按需求检索可调用接口。"
                ),
                user_prompt=API_SUMMARY_PROMPT,
                user_question=content,
            )
            chunks: List[str] = []
            async for chunk in stream:
                chunks.append(chunk)
            full = "".join(chunks).strip()
            if _is_stream_error_text(full):
                return ApiSummaryService.fallback_summary(api)
            return full
        except Exception as e:
            logging.error("Lib API 摘要失败 name=%s error=%s", api.display_name(), e)
            return ApiSummaryService.fallback_summary(api)

    @staticmethod
    def _build_llm_input(api: PublicApi) -> str:
        parts = [
            f"语言: {api.language}",
            f"类型: {api.kind}",
            f"名称: {api.display_name()}",
            f"签名: {api.signature}",
        ]
        if api.params:
            parts.append(f"参数: {', '.join(api.params)}")
        if api.param_types:
            parts.append(f"参数类型: {', '.join(api.param_types)}")
        if api.return_types:
            parts.append(f"返回类型: {', '.join(api.return_types)}")
        if api.docstring:
            parts.append(f"文档: {api.docstring}")
        src = (api.source_code or "").strip()
        if src:
            parts.append(f"源码:\n{src[:4000]}")
        return "\n".join(parts)

    @staticmethod
    def fallback_summary(api: PublicApi) -> str:
        doc = (api.docstring or "").strip()
        if doc:
            return f"功能：{doc[:180]}\n关键参数：{api.signature}\n返回：{'/'.join(api.return_types) or '无'}"
        return (
            f"功能：公开接口 {api.display_name()}（摘要回退）\n"
            f"关键参数：{api.signature}\n"
            f"返回：{'/'.join(api.return_types) or '无'}"
        )
