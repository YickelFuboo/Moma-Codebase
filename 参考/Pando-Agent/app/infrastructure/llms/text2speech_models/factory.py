from typing import Dict, Type
from app.infrastructure.llms.base_factory import BaseModelFactory
from .base import BaseTTS
from .openai_tts import OpenAITTS
from .fish_audio_tts import FishAudioTTS
from .qwen_tts import QwenTTS
from .spark_tts import SparkTTS
from .siliconflow_tts import SiliconFlowTTS
from .xinference_tts import XinferenceTTS
from .gpustack_tts import GPUStackTTS
from .ollama_tts import OllamaTTS


class TTSFactory(BaseModelFactory[BaseTTS]):
    """TTS模型工厂类"""
    
    @property
    def _models(self) -> Dict[str, Type[BaseTTS]]:
        return {
            "openai": OpenAITTS,
            "fish_audio": FishAudioTTS,
            "qwen": QwenTTS,
            "spark": SparkTTS,
            "siliconflow": SiliconFlowTTS,
            "xinference": XinferenceTTS,
            "gpustack": GPUStackTTS,
            "ollama": OllamaTTS,
        }

    def __init__(self):
        super().__init__("tts_models.json")


# 全局工厂实例
tts_factory = TTSFactory()
