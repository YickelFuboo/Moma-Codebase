from fastapi import WebSocket
from typing import Dict
from enum import Enum
import logging


class WebSocketMessageType(Enum):
    """消息类型"""
    # 连接成功
    CONNECT_SUCCESS = "connect_success"
    # 连接失败
    CONNECT_ERROR = "connect_error"
    # 断开连接
    DISCONNECT = "disconnect"
    # 处理通知
    RESPONSE = "response"
    STREAM_START = "stream_start"
    STREAM_DELTA = "stream_delta"
    STREAM_END = "stream_end"
    RUN_END = "run_end"
    ERROR = "error"

class WebSocketMessage:
    """WebSocket 下发给客户端的消息。"""
    message_type: WebSocketMessageType
    session_id: str
    content: str

    def __init__(self, message_type: WebSocketMessageType, session_id: str, content: str):
        self.message_type = message_type
        self.session_id = session_id
        self.content = content

    def to_dict(self):
        return {
            "message_type": self.message_type.value,
            "session_id": self.session_id,
            "content": self.content,
        }

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        """建立新的WebSocket连接"""
        logging.info(f"WebSocket connecting: {client_id}")
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logging.info(f"WebSocket connected: {client_id}")
        
    async def disconnect(self, client_id: str):
        """关闭WebSocket连接"""
        logging.info(f"WebSocket disconnecting: {client_id}")
        try:
            if client_id in self.active_connections:
                await self.active_connections[client_id].close()
                del self.active_connections[client_id]
                logging.info(f"WebSocket disconnected: {client_id}")    
        except Exception as e:
            logging.info(f"Error closing connection: {str(e)}")
            
    def get_handler(self, client_id: str) -> WebSocket:
        """获取WebSocket处理器"""
        return self.active_connections.get(client_id)
         
    async def send_message(self, client_id: str, message: WebSocketMessage):
        """发送消息到客户端"""
        logging.info(f"Sending {message.message_type} to {client_id}")
        
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message.to_dict())
                logging.info(f"Message sent successfully")
            except Exception as e:
                logging.info(f"Error sending message: {str(e)}")
                await self.disconnect(client_id)
        else:
            raise Exception(f"No active connection for {client_id}")

    async def get_websocket(self, client_id: str) -> WebSocket:
        """获取WebSocket"""
        if client_id not in self.active_connections:
            raise Exception(f"No active connection for {client_id}")
        
        return self.active_connections.get(client_id)

WEBSOCKET_MANAGER = WebSocketManager()