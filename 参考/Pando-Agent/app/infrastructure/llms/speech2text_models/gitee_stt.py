from typing import Any, Optional
import asyncio
import logging
from openai import AsyncOpenAI
from .base import BaseSTT, MAX_RETRY_ATTEMPTS, CONNECTION_TIMEOUT


class GiteeSTT(BaseSTT):
    """GiteeAI的语音转文本模型实现"""

    def __init__(self, api_key: str, model_provider: str, model_name: str = "whisper-1", base_url: Optional[str] = None, **kwargs):
        """
        初始化GiteeAI语音转文本模型
        
        Args:
            api_key (str): GiteeAI API密钥
            model_provider (str): 模型提供商
            model_name (str): 模型名称，默认为whisper-1
            base_url (Optional[str]): API基础URL，默认为GiteeAI官方URL
        """
        if not base_url:
            base_url = "https://ai.gitee.com/v1/"
        
        super().__init__(api_key, model_provider, model_name, base_url, **kwargs)

        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=CONNECTION_TIMEOUT)

    async def stt(self, audio: Any, **kwargs) -> tuple[str, int]:
        """
        将音频转录为文本
        
        Args:
            audio: 音频文件对象
            **kwargs: 其他参数
            
        Returns:
            tuple: (转录文本, 输入音频的token等价量)
            
        Raises:
            Exception: 当API请求失败时
            
        语言支持方式:
            - 基于Whisper模型，自动检测语言
            - 支持多语言自动识别
            - 包括中文、英文、日文、韩文等
        """
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                transcription = await self.client.audio.transcriptions.create(
                    model=self.model_name, 
                    file=audio, 
                    response_format="text"
                )
                text = transcription.text.strip()
                
                return text, self._total_token_count(transcription, audio)
            
            except Exception as e:
                if attempt < MAX_RETRY_ATTEMPTS - 1 and self._is_retryable_error(e):
                    delay = self._get_delay(attempt)
                    logging.warning(f"Gitee STT失败，重试 (尝试 {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}. 等待 {delay:.2f}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logging.error(f"Gitee STT最终失败: {e}")
                    raise Exception(f"**ERROR**: {e}")