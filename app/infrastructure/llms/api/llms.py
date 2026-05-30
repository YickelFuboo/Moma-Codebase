from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Form
from fastapi.responses import StreamingResponse
from app.infrastructure.llms import llm_factory, embedding_factory

router = APIRouter(prefix="/models", tags=["模型管理"])


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


class EmbeddingRequest(ModelRequest):
    """嵌入请求"""
    texts: List[str]


class EmbeddingResponse(BaseModel):
    """嵌入响应"""
    embeddings: List[List[float]]
    token_count: int


@router.get("/", summary="获取所有支持的模型列表")
async def get_all_models():
    """获取聊天与嵌入模型列表。"""
    try:
        return {
            "chat_models": llm_factory.get_supported_models(),
            "embedding_models": embedding_factory.get_supported_models(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


@router.get("/available/chat", summary="获取可用聊天模型列表")
async def get_chat_models():
    return llm_factory.get_supported_models()


@router.get("/available/embedding", summary="获取可用嵌入模型列表")
async def get_embedding_models():
    return embedding_factory.get_supported_models()


@router.post("/chat", summary="聊天对话", tags=["聊天模型"])
async def chat(request: ChatRequest):
    try:
        model = llm_factory.create_model(request.provider, request.model_name)
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        response, _usage = await model.chat(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            user_question=request.user_question,
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"聊天请求失败: {str(e)}")


@router.post("/chat/stream", summary="流式聊天对话", tags=["聊天模型"])
async def chat_stream(request: ChatRequest):
    try:
        model = llm_factory.create_model(request.provider, request.model_name)
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")

        async def generate():
            stream_generator, _usage = await model.chat_stream(
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                user_question=request.user_question,
            )
            async for chunk in stream_generator:
                yield f"data: {chunk}\n\n"

        return StreamingResponse(generate(), media_type="text/plain")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"流式聊天请求失败: {str(e)}")


@router.post("/embedding/encode", response_model=EmbeddingResponse, summary="文本编码", tags=["嵌入模型"])
async def encode_texts(request: EmbeddingRequest):
    try:
        model = embedding_factory.create_model(request.provider, request.model_name)
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        embeddings = await model.encode_texts(request.texts)
        return EmbeddingResponse(
            embeddings=embeddings,
            token_count=sum(len(text.split()) for text in request.texts),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文本编码失败: {str(e)}")


@router.post("/embedding/encode-query", summary="查询文本编码", tags=["嵌入模型"])
async def encode_query(request: ModelRequest, query: str = Form(...)):
    try:
        model = embedding_factory.create_model(request.provider, request.model_name)
        if not model:
            raise HTTPException(status_code=400, detail="无法创建模型实例")
        embedding = await model.encode_query(query)
        return {
            "embedding": embedding,
            "token_count": len(query.split()),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询文本编码失败: {str(e)}")
