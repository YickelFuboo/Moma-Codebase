from pydantic import BaseModel
from typing import Optional, Dict, Any

class UserRequest(BaseModel):
    """用户请求"""
    session_id: str
    user_id: str
    content: str
    agent_type: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    workspace_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class UserResponse(BaseModel):
    """用户响应"""
    session_id: str
    content: str
