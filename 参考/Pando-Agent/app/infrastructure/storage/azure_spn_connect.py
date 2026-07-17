import time
import asyncio
from io import BytesIO
from typing import Optional, BinaryIO, Dict, Any
import logging
from azure.identity import ClientSecretCredential, AzureAuthorityHosts
from azure.storage.filedatalake import FileSystemClient
from azure.core.exceptions import AzureError
from app.infrastructure.storage.base import StorageBase
from app.config.settings import APP_NAME

# 常量定义
ATTEMPT_TIME = 3
RETRY_DELAY = 1

class AzureSpnStorage(StorageBase):
    """Azure SPN存储实现"""
    
    def __init__(self, account_url: str, client_id: str, client_secret: str, tenant_id: str, container_name: str):
        """
        初始化Azure SPN存储
        
        Args:
            account_url: Azure存储账户URL
            client_id: 客户端ID
            client_secret: 客户端密钥
            tenant_id: 租户ID
            container_name: 容器名称
        """
        self.account_url = account_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.default_bucket_name = APP_NAME.lower().replace("_", "-")
        self.container_name = container_name
        
        self.client = None
        self._last_health_check: float = 0
        self._health_check_interval: int = 30
        self._connection_lock = asyncio.Lock()
        
        logging.info("Azure SPN存储初始化完成")
    
    async def put(self, file_index: str, file_data: BinaryIO, 
                  bucket_name: Optional[str] = None,
                  content_type: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> str:
        """上传文件到Azure SPN"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 读取文件数据
            binary_data = file_data.read()
            
            for attempt in range(ATTEMPT_TIME):
                try:
                    f = await asyncio.to_thread(self.client.create_file, file_index)
                    await asyncio.to_thread(f.append_data, binary_data, offset=0, length=len(binary_data))
                    await asyncio.to_thread(f.flush_data, len(binary_data))
                    logging.info(f"文件上传成功: {bucket_name}/{file_index}")
                    return file_index
                    
                except Exception as e:
                    if attempt < ATTEMPT_TIME - 1 and self._should_retry(e):
                        logging.warning(f"上传失败，重试 {attempt + 1}/{ATTEMPT_TIME}: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logging.error(f"文件上传失败: {e}")
                        raise
            
        except Exception as e:
            logging.error(f"文件上传失败: {e}")
            raise
    
    async def get(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[BinaryIO]:
        """从Azure SPN下载文件"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            for attempt in range(ATTEMPT_TIME):
                try:
                    client = await asyncio.to_thread(self.client.get_file_client, file_index)
                    r = await asyncio.to_thread(client.download_file)
                    return BytesIO(await asyncio.to_thread(r.read))
                
                except Exception as e:
                    if attempt < ATTEMPT_TIME - 1 and self._should_retry(e):
                        logging.warning(f"下载失败，重试 {attempt + 1}/{ATTEMPT_TIME}: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logging.error(f"下载文件失败: {e}")
                        return None
            
        except Exception as e:
            logging.error(f"下载文件失败: {e}")
            return None
    
    async def delete(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """删除Azure SPN文件"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            for attempt in range(ATTEMPT_TIME):
                try:
                    await asyncio.to_thread(self.client.delete_file, file_index)
                    logging.info(f"文件删除成功: {file_index}")
                    return True
                except Exception as e:
                    if attempt < ATTEMPT_TIME - 1 and self._should_retry(e):
                        logging.warning(f"删除失败，重试 {attempt + 1}/{ATTEMPT_TIME}: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logging.error(f"删除文件失败: {e}")
                        return False
            
        except Exception as e:
            logging.error(f"删除文件失败: {e}")
            return False
    
    async def get_url(self, file_index: str, bucket_name: Optional[str] = None, expires_in: Optional[int] = None) -> Optional[str]:
        """获取文件访问URL"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            for attempt in range(ATTEMPT_TIME):
                try:
                    url = await asyncio.to_thread(
                        self.client.get_presigned_url, "GET", bucket_name, file_index, expires_in or 3600
                    )
                    return url
                except Exception as e:
                    if attempt < ATTEMPT_TIME - 1 and self._should_retry(e):
                        logging.warning(f"获取URL失败，重试 {attempt + 1}/{ATTEMPT_TIME}: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logging.error(f"获取文件URL失败: {e}")
                        return None
            
        except Exception as e:
            logging.error(f"获取文件URL失败: {e}")
            return None
    
    async def exists(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """检查文件是否存在"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            for attempt in range(ATTEMPT_TIME):
                try:
                    client = await asyncio.to_thread(self.client.get_file_client, file_index)
                    return await asyncio.to_thread(client.exists)
                except Exception as e:
                    if attempt < ATTEMPT_TIME - 1 and self._should_retry(e):
                        logging.warning(f"检查存在性失败，重试 {attempt + 1}/{ATTEMPT_TIME}: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logging.error(f"检查文件存在性失败: {e}")
                        return False
            
        except Exception as e:
            logging.error(f"检查文件存在性失败: {e}")
            return False
    
    async def get_metadata(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取文件元数据"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            for attempt in range(ATTEMPT_TIME):
                try:
                    client = await asyncio.to_thread(self.client.get_file_client, file_index)
                    properties = await asyncio.to_thread(client.get_file_properties)
                    
                    return {
                        'file_index': file_index,
                        'bucket_name': bucket_name,
                        'file_size': properties.size,
                        'last_modified': properties.last_modified,
                        'content_type': properties.content_type,
                        'metadata': properties.metadata
                    }
                except Exception as e:
                    if attempt < ATTEMPT_TIME - 1 and self._should_retry(e):
                        logging.warning(f"获取元数据失败，重试 {attempt + 1}/{ATTEMPT_TIME}: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logging.error(f"获取文件元数据失败: {e}")
                        return None
            
        except Exception as e:
            logging.error(f"获取文件元数据失败: {e}")
            return None
    
    async def health_check(self) -> bool:
        """健康检查"""
        await self._ensure_connect()
        try:
            # 尝试上传一个测试文件
            test_data = b"health check test"
            test_file_index = "__health_check_test__"
            test_bucket = self.default_bucket_name
            
            # 上传测试文件
            await self.put(test_file_index, BytesIO(test_data), bucket_name=test_bucket)
            
            # 检查文件是否存在
            exists = await self.exists(test_file_index, bucket_name=test_bucket)
            
            # 删除测试文件
            await self.delete(test_file_index, bucket_name=test_bucket)
            
            return exists
            
        except Exception as e:
            logging.error(f"Azure SPN健康检查失败: {e}")
            return False
    
    async def close(self):
        """断开连接"""
        try:
            if self.client:
                del self.client
                self.client = None
                logging.info("Azure SPN连接已关闭")
        except Exception as e:
            logging.error(f"关闭Azure SPN连接失败: {e}")

    async def _ensure_connect(self):
        """
        确保连接已建立且健康 - 供业务方法调用
        """
        # 1. 检查连接是否存在
        if self.client is None:
            async with self._connection_lock:
                if self.client is None:  # 双重检查锁定
                    await self._connect()
        
        # 2. 检查连接是否健康
        if self._should_check_health():
            try:
                if not await self._health_check():
                    logging.warning("Azure SPN连接不健康，重新连接")
                    async with self._connection_lock:
                        await self._connect()  # 重新连接
            except Exception as e:
                logging.warning(f"Azure SPN连接健康检查失败: {e}，重新连接")
                async with self._connection_lock:
                    await self._connect()  # 重新连接
            self._last_health_check = time.time()

    async def _connect(self):
        """建立Azure SPN连接"""
        # 先关闭现有连接
        if self.client:
            try:
                del self.client
            except:
                pass
            self.client = None

        # 重新创建连接
        for attempt in range(ATTEMPT_TIME):   
            try:
                credentials = ClientSecretCredential(
                    tenant_id=self.tenant_id,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    authority=AzureAuthorityHosts.AZURE_CHINA
                )
                self.client = FileSystemClient(
                    account_url=self.account_url,
                    file_system_name=self.container_name,
                    credential=credentials
                )

                # 测试连接
                if await self._health_check():
                    logging.info(f"Connected to Azure SPN {self.account_url}")
                    return  # 连接成功，直接返回
                else:
                    logging.warning(f"Azure SPN {self.account_url} 连接失败，等待重试...")
            
            except asyncio.CancelledError:
                logging.error(f"Azure SPN连接被取消: {self.account_url}")
                raise
            except Exception as e:
                logging.warning(f"Azure SPN {self.account_url} 连接异常: {e}")

            if attempt < ATTEMPT_TIME - 1:  # 不是最后一次尝试
                await asyncio.sleep(RETRY_DELAY)
        
        # 如果所有重试都失败了
        msg = f"Azure SPN {self.account_url} 连接失败，已尝试 {ATTEMPT_TIME} 次"
        logging.error(msg)
        raise ConnectionError(msg)
    
    def _should_check_health(self) -> bool:
        """判断是否需要健康检查"""
        return time.time() - self._last_health_check > self._health_check_interval

    async def _health_check(self) -> bool:
        """内部健康检查方法"""
        try:
            if self.client:
                # 尝试获取文件系统属性来验证连接
                await asyncio.to_thread(self.client.get_file_system_properties)
                return True
            return False
        except Exception as e:
            logging.error(f"Azure SPN健康检查失败: {e}")
            return False

    def _get_bucket_name(self, bucket_name: Optional[str]) -> str:
        """获取bucket名称"""
        return bucket_name or self.default_bucket_name

    def _should_retry(self, exception: Exception) -> bool:
        """判断异常是否需要重试"""
        # 网络超时错误需要重试
        if hasattr(exception, 'status_code') and exception.status_code in [408, 429, 500, 502, 503, 504]:
            return True
        
        # 连接错误需要重试
        if hasattr(exception, '__class__'):
            error_name = exception.__class__.__name__.lower()
            if any(keyword in error_name for keyword in ['timeout', 'connection', 'network', 'socket']):
                return True
        
        # 其他临时性错误需要重试
        if hasattr(exception, 'status_code') and exception.status_code >= 500:
            return True
        
        # 默认不重试（包括404、401、403等）
        return False