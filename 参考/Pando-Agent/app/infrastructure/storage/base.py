from typing import Optional, BinaryIO, Dict, Any
from abc import ABC, abstractmethod

class StorageBase(ABC):
    """存储基类"""
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            bool: 存储服务是否健康
        """
        pass
    
    @abstractmethod
    async def close(self):
        """
        关闭连接
        
        清理资源，关闭连接
        """
        pass
    
    @abstractmethod
    async def put(self, file_index: str, file_data: BinaryIO, 
                  bucket_name: Optional[str] = None,
                  content_type: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        上传文件
        
        Args:
            file_index: 文件索引（可以是路径、ID、键值等）
            file_data: 文件数据
            bucket_name: 存储桶名称（可选，默认使用应用名称）
            content_type: 内容类型（可选，如image/jpeg、text/plain等）
            metadata: 元数据
        
        Returns:
            str: 文件标识符
        """
        pass
    
    @abstractmethod
    async def get(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[BinaryIO]:
        """
        下载文件
        
        Args:
            file_index: 文件索引（可以是路径、ID、键值等）
            bucket_name: 存储桶名称（可选，默认使用应用名称）
        
        Returns:
            Optional[BinaryIO]: 文件数据
        """
        pass
    
    @abstractmethod
    async def delete(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """
        删除文件
        
        Args:
            file_index: 文件索引（可以是路径、ID、键值等）
            bucket_name: 存储桶名称（可选，默认使用应用名称）
        
        Returns:
            bool: 是否删除成功
        """
        pass
    
    @abstractmethod
    async def get_url(self, file_index: str, bucket_name: Optional[str] = None, expires_in: Optional[int] = None) -> Optional[str]:
        """
        获取文件访问URL
        
        Args:
            file_index: 文件索引（可以是路径、ID、键值等）
            bucket_name: 存储桶名称（可选，默认使用应用名称）
            expires_in: 过期时间（秒）
        
        Returns:
            Optional[str]: 文件URL
        """
        pass
    
    @abstractmethod
    async def exists(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """
        检查文件是否存在
        
        Args:
            file_index: 文件索引（可以是路径、ID、键值等）
            bucket_name: 存储桶名称（可选，默认使用应用名称）
        
        Returns:
            bool: 文件是否存在
        """
        pass
    
    @abstractmethod
    async def get_metadata(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取文件元数据
        
        Args:
            file_index: 文件索引（可以是路径、ID、键值等）
            bucket_name: 存储桶名称（可选，默认使用应用名称）
        
        Returns:
            Optional[Dict[str, Any]]: 文件元数据
        """
        pass
