import asyncio
import base64
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.config.settings import MODELS_CONFIG_DIR
from app.infrastructure.llms import cv_factory, embedding_factory, llm_factory, rerank_factory, stt_factory, tts_factory


# 主路由
router = APIRouter(prefix="/models", tags=["模型管理"])


# ==================== 数据模型 ====================

class ModelRequest(BaseModel):
    """通用模型请求"""
    model_config = {"protected_namespaces": ()}
    
    provider: Optional[str] = None
    model_name: Optional[str] = None


class ChatRequest(ModelRequest):
    """聊天请求"""
    system_prompt: Optional[str] = None
    user_prompt: str
    user_question: str


class ChatResponse(BaseModel):
    """聊天响应"""
    content: str
    token_count: int


class ImageDescribeRequest(ModelRequest):
    """图像描述请求"""
    image_base64: str


class ImageDescribeWithPromptRequest(ModelRequest):
    """带提示词的图像描述请求"""
    image_base64: str
    prompt: str


class ImageChatRequest(ModelRequest):
    """图像聊天请求（支持普通和流式）"""
    image_base64: str
    user_question: str


class EmbeddingRequest(ModelRequest):
    """嵌入请求"""
    texts: List[str]


class EmbeddingResponse(BaseModel):
    """嵌入响应"""
    embeddings: List[List[float]]
    token_count: int


class RerankRequest(ModelRequest):
    """重排序请求"""
    query: str
    texts: List[str]


class RerankResponse(BaseModel):
    """重排序响应"""
    similarities: List[float]


class TTSRequest(ModelRequest):
    """文本转语音请求"""
    text: str
    voice: Optional[str] = None


class ModelConfigUpdateRequest(BaseModel):
    """模型配置文件更新请求"""
    config: Dict[str, Any]


MODEL_TYPE_META: Dict[str, Dict[str, str]] = {
    "chat": {"label": "聊天模型", "filename": "chat_models.json"},
    "embedding": {"label": "嵌入模型", "filename": "embedding_models.json"},
    "rerank": {"label": "重排模型", "filename": "rerank_models.json"},
    "cv": {"label": "视觉模型", "filename": "cv_models.json"},
    "stt": {"label": "语音转文本", "filename": "stt_models.json"},
    "tts": {"label": "文字转语音", "filename": "tts_models.json"},
}


class ModelConfigError(Exception):
    pass


def list_model_types() -> List[Dict[str, str]]:
    return [
        {"id": key, "label": meta["label"], "filename": meta["filename"]}
        for key, meta in MODEL_TYPE_META.items()
    ]


def _config_path(model_type: str) -> Path:
    meta = MODEL_TYPE_META.get(model_type)
    if not meta:
        raise ModelConfigError(f"不支持的模型类型: {model_type}")
    return MODELS_CONFIG_DIR / meta["filename"]


def _normalize_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ModelConfigError("配置须为 JSON 对象")
    models = raw.get("models")
    if models is None:
        raw["models"] = {}
    elif not isinstance(models, dict):
        raise ModelConfigError("models 须为对象")
    default = raw.get("default")
    if default is None:
        raw["default"] = {"provider": "", "model": ""}
    elif not isinstance(default, dict):
        raise ModelConfigError("default 须为对象")
    return raw


def get_model_config(model_type: str) -> Dict[str, Any]:
    path = _config_path(model_type)
    if not path.is_file():
        raise ModelConfigError(f"配置文件不存在: {path.name}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ModelConfigError(f"配置文件格式错误: {e}") from e
    return _normalize_config(data)


def save_model_config(model_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    path = _config_path(model_type)
    normalized = _normalize_config(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _reload_factory(model_type)
    return normalized


def _reload_factory(model_type: str) -> None:
    factory_map = {
        "chat": llm_factory,
        "embedding": embedding_factory,
        "rerank": rerank_factory,
        "cv": cv_factory,
        "stt": stt_factory,
        "tts": tts_factory,
    }
    factory = factory_map.get(model_type)
    if not factory:
        return
    factory.load_config()
    factory.clear_instance_cache()


# ==================== 主路由 - 模型列表查询 ====================

@router.get("/", summary="获取所有支持的模型列表")
async def get_all_models():
    """获取所有功能模块支持的模型列表（含 supported 与 default）。"""
    try:
        return {
            "chat_models": llm_factory.get_supported_models(),
            "cv_models": cv_factory.get_supported_models(),
            "embedding_models": embedding_factory.get_supported_models(),
            "rerank_models": rerank_factory.get_supported_models(),
            "stt_models": stt_factory.get_supported_models(),
            "tts_models": tts_factory.get_supported_models(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


@router.get("/available/chat", summary="获取可用聊天模型列表")
async def get_chat_models():
    """获取可用聊天模型列表及默认模型。"""
    return llm_factory.get_supported_models()


@router.get("/available/cv", summary="获取可用计算机视觉模型列表")
async def get_cv_models():
    """获取可用计算机视觉模型列表及默认模型。"""
    return cv_factory.get_supported_models()


@router.get("/available/embedding", summary="获取可用嵌入模型列表")
async def get_embedding_models():
    """获取可用嵌入模型列表及默认模型。"""
    return embedding_factory.get_supported_models()


@router.get("/available/rerank", summary="获取可用重排序模型列表")
async def get_rerank_models():
    """获取可用重排序模型列表及默认模型。"""
    return rerank_factory.get_supported_models()


@router.get("/available/stt", summary="获取可用语音转文本模型列表")
async def get_stt_models():
    """获取可用语音转文本模型列表及默认模型。"""
    return stt_factory.get_supported_models()


@router.get("/available/tts", summary="获取可用文本转语音模型列表")
async def get_tts_models():
    """获取可用文本转语音模型列表及默认模型。"""
    return tts_factory.get_supported_models()


@router.get("/config/types", summary="获取可配置的模型类型列表")
async def get_model_config_types():
    """返回 data/models 下各模型配置文件类型。"""
    return {"items": list_model_types()}


@router.get("/config/{model_type}", summary="读取模型配置文件")
async def get_model_config_api(model_type: str):
    """读取指定类型的完整模型配置（含未启用的 Provider）。"""
    try:
        return {
            "model_type": model_type,
            "config": get_model_config(model_type),
        }
    except ModelConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/config/{model_type}", summary="保存模型配置文件")
async def update_model_config_api(model_type: str, body: ModelConfigUpdateRequest):
    """保存模型配置并热重载对应工厂。"""
    try:
        config = save_model_config(model_type, body.config)
        return {
            "model_type": model_type,
            "config": config,
        }
    except ModelConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ==================== 聊天模型API ====================

@router.post("/chat", summary="聊天对话", tags=["聊天模型"])
async def chat(request: ChatRequest):
    """聊天对话接口"""
    try:
        model = llm_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        response, usage = await model.chat(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            user_question=request.user_question
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"聊天请求失败: {str(e)}")


@router.post("/chat/stream", summary="流式聊天对话", tags=["聊天模型"])
async def chat_stream(request: ChatRequest):
    """流式聊天对话接口"""
    try:
        model = llm_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        async def generate():
            stream_generator, _usage = await model.chat_stream(
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                user_question=request.user_question
            )
            async for chunk in stream_generator:
                yield f"data: {chunk}\n\n"
        
        return StreamingResponse(generate(), media_type="text/plain")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"流式聊天请求失败: {str(e)}")


# ==================== 计算机视觉模型API ====================

@router.post("/cv/describe", summary="图像描述", tags=["计算机视觉模型"])
async def describe_image(request: ImageDescribeRequest):
    """图像描述接口"""
    try:
        model = cv_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        # 解码base64图像
        image_data = base64.b64decode(request.image_base64)
        
        result = await model.describe(image_data)
        
        return {
            "description": result,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图像描述失败: {str(e)}")


@router.post("/cv/describe-with-prompt", summary="带提示词的图像描述", tags=["计算机视觉模型"])
async def describe_image_with_prompt(request: ImageDescribeWithPromptRequest):
    """带提示词的图像描述接口"""
    try:
        model = cv_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        # 解码base64图像
        image_data = base64.b64decode(request.image_base64)
        
        result = await model.describe_with_prompt(image_data, request.prompt)
        
        return {
            "description": result,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"带提示词图像描述失败: {str(e)}")


@router.post("/cv/chat", summary="图像聊天", tags=["计算机视觉模型"])
async def image_chat(request: ImageChatRequest):
    """图像聊天接口"""
    try:
        model = cv_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        # 解码base64图像
        image_data = base64.b64decode(request.image_base64)
        
        result = await model.chat(image_data, request.user_question)
        
        return {
            "response": result,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图像聊天失败: {str(e)}")


@router.post("/cv/chat/stream", summary="图像流式聊天", tags=["计算机视觉模型"])
async def image_chat_stream(request: ImageChatRequest):
    """图像流式聊天接口"""
    try:
        model = cv_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        # 解码base64图像
        image_data = base64.b64decode(request.image_base64)
        
        async def generate():
            async for chunk in model.chat_stream(image_data, request.user_question):
                yield f"data: {chunk}\n\n"
        
        return StreamingResponse(generate(), media_type="text/plain")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图像流式聊天失败: {str(e)}")


# ==================== 嵌入模型API ====================

@router.post("/embedding/encode", response_model=EmbeddingResponse, summary="文本编码", tags=["嵌入模型"])
async def encode_texts(request: EmbeddingRequest):
    """文本编码接口"""
    try:
        model = embedding_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        embeddings = await model.encode_texts(request.texts)
        
        return EmbeddingResponse(
            embeddings=embeddings,
            token_count=sum(len(text.split()) for text in request.texts)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文本编码失败: {str(e)}")


@router.post("/embedding/encode-query", summary="查询文本编码", tags=["嵌入模型"])
async def encode_query(request: ModelRequest, query: str = Form(...)):
    """查询文本编码接口"""
    try:
        model = embedding_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        embedding = await model.encode_query(query)
        
        return {
            "embedding": embedding,
            "token_count": len(query.split()),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询文本编码失败: {str(e)}")


# ==================== 重排序模型API ====================

@router.post("/rerank/similarity", response_model=RerankResponse, summary="相似度计算", tags=["重排序模型"])
async def calculate_similarity(request: RerankRequest):
    """相似度计算接口"""
    try:
        model = rerank_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        similarities = await model.similarity(request.query, request.texts)
        
        return RerankResponse(
            similarities=similarities
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"相似度计算失败: {str(e)}")


# ==================== 语音转文本模型API ====================

@router.post("/stt/transcribe", summary="语音转文本", tags=["语音转文本模型"])
async def transcribe_audio(audio_file: UploadFile = File(...), provider: Optional[str] = Form(None), model: Optional[str] = Form(None)):
    """语音转文本接口"""
    try:
        stt_model = stt_factory.create_model(provider, model)
        
        if not stt_model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        # 读取音频文件
        audio_data = await audio_file.read()
        
        # 根据模型类型处理音频数据
        if hasattr(stt_model, '_prepare_audio_input'):
            # 对于QwenSTT等需要特殊处理的模型
            audio_input = stt_model._prepare_audio_input(audio_data)
        else:
            # 对于其他模型，直接使用字节数据
            audio_input = audio_data
        
        result = await stt_model.stt(audio_input)
        
        return {
            "text": result,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语音转文本失败: {str(e)}")


# ==================== 文本转语音模型API ====================

@router.post("/tts/synthesize", summary="文本转语音", tags=["文本转语音模型"])
async def synthesize_speech(request: TTSRequest):
    """文本转语音接口"""
    try:
        model = tts_factory.create_model(request.provider, request.model_name)
        
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        
        # 调用TTS模型
        audio_gen, token_count = await model.tts(request.text, voice=request.voice)
        
        # 收集音频数据
        audio_data = b''
        for chunk in audio_gen:
            audio_data += chunk
        
        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=synthesized_audio.wav",
                "X-Token-Count": str(token_count),
                "X-Model-Used": f"{request.provider or 'default'}/{request.model_name or 'default'}"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文本转语音失败: {str(e)}")

