import asyncio
import time
from datetime import timedelta
from typing import Optional, BinaryIO, Dict, Any
from minio import Minio
import logging
from app.infrastructure.storage.base import StorageBase
from app.config.settings import APP_NAME

# 重试次数常量
ATTEMPT_TIME = 3
RETRY_DELAY = 2  # 重试间隔（秒）


class MinIOStorage(StorageBase):
    """MinIO存储实现"""
    
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = True):
        """
        初始化MinIO存储
        
        Args:
            endpoint: MinIO服务端点
            access_key: 访问密钥
            secret_key: 秘密密钥
            secure: 是否使用HTTPS
        """
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure
        self.default_bucket_name = APP_NAME.lower().replace("_", "-")

        self.client = None
        self._last_health_check: float = 0
        self._health_check_interval: int = 30
        self._connection_lock = asyncio.Lock()
        
        # 验证endpoint格式
        if not endpoint:
            raise ValueError("MinIO endpoint不能为空")
        
        # 如果endpoint包含协议，提取主机和端口
        if endpoint.startswith(('http://', 'https://')):
            # 移除协议前缀
            endpoint = endpoint.split('://', 1)[1]
            logging.info(f"MinIO endpoint包含协议前缀，已自动移除: {endpoint}")
        
        logging.info(f"MinIO存储初始化完成: {self.endpoint}")
    
    async def put(self, file_index: str, file_data: BinaryIO, 
                  bucket_name: Optional[str] = None,
                  content_type: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> str:
        """上传文件到MinIO"""
        await self._ensure_connect()
        
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 确保bucket存在
            await self._ensure_bucket_exists(bucket_name)
            
            # 使用传入的file_index作为对象键
            object_key = file_index
            
            # 准备metadata，确保所有值都是ASCII编码
            minio_metadata = {}
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, str):
                        # 对非ASCII字符进行URL编码
                        try:
                            value.encode('ascii')
                            minio_metadata[key] = value
                        except UnicodeEncodeError:
                            # 如果包含非ASCII字符，进行URL编码
                            import urllib.parse
                            minio_metadata[key] = urllib.parse.quote(value, safe='')
                    else:
                        minio_metadata[key] = str(value)
            
            # 获取文件数据大小
            file_data.seek(0, 2)  # 移动到文件末尾
            file_size = file_data.tell()  # 获取文件大小
            file_data.seek(0)  # 重置到文件开头
            
            # 上传文件到MinIO（使用asyncio.to_thread避免阻塞事件循环）
            await asyncio.to_thread(
                self.client.put_object,
                bucket_name,
                object_key,
                file_data,
                length=file_size,  # 使用实际文件大小
                content_type=content_type or "application/octet-stream",  # 默认类型
                metadata=minio_metadata
            )
            
            logging.info(f"文件上传成功: {bucket_name}/{object_key}")
            return file_index
            
        except Exception as e:
            logging.error(f"文件上传失败: {e}")
            raise
    
    async def get(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[BinaryIO]:
        """从MinIO下载文件"""
        await self._ensure_connect()
        
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 直接使用file_index作为对象键（使用asyncio.to_thread避免阻塞事件循环）
            response = await asyncio.to_thread(self.client.get_object, bucket_name, file_index)
            return response
            
        except Exception as e:
            logging.error(f"下载文件失败: {e}")
            return None
    
    async def delete(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """删除MinIO文件"""
        await self._ensure_connect()
        
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            await asyncio.to_thread(self.client.remove_object, bucket_name, file_index)
            logging.info(f"文件删除成功: {bucket_name}/{file_index}")
            return True
            
        except Exception as e:
            logging.error(f"删除文件失败: {e}")
            return False
    
    async def get_url(self, file_index: str, bucket_name: Optional[str] = None, expires_in: Optional[int] = None) -> Optional[str]:
        """获取文件访问URL"""
        await self._ensure_connect()
        
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 生成预签名URL（使用asyncio.to_thread避免阻塞事件循环）
            url = await asyncio.to_thread(
                self.client.presigned_get_object,
                bucket_name,
                file_index,
                expires=timedelta(seconds=expires_in or 3600)  # 默认1小时
            )
            return url
            
        except Exception as e:
            logging.error(f"获取文件URL失败: {e}")
            return None
    
    async def exists(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """检查文件是否存在"""
        await self._ensure_connect()
        
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            await asyncio.to_thread(self.client.stat_object, bucket_name, file_index)
            return True
        except Exception:
            return False
    
    async def get_metadata(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取文件元数据"""
        await self._ensure_connect()
        
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            stat = await asyncio.to_thread(self.client.stat_object, bucket_name, file_index)
            
            # 解码元数据中的URL编码字符
            decoded_metadata = {}
            if stat.metadata:
                import urllib.parse
                for key, value in stat.metadata.items():
                    if isinstance(value, str):
                        try:
                            # 尝试解码URL编码的字符
                            decoded_metadata[key] = urllib.parse.unquote(value)
                        except:
                            decoded_metadata[key] = value
                    else:
                        decoded_metadata[key] = value
            
            return {
                'file_index': file_index,
                'bucket_name': bucket_name,
                'file_size': stat.size,
                'last_modified': stat.last_modified,
                'content_type': stat.content_type,
                'metadata': decoded_metadata
            }
        except Exception as e:
            logging.error(f"获取文件元数据失败: {e}")
            return None
             
    async def health_check(self) -> bool:
        """健康检查"""
        await self._ensure_connect()

        return await self._health_check()        

    async def close(self):
        """关闭连接"""
        try:
            if self.client:
                if hasattr(self.client, 'close'):
                    await asyncio.to_thread(self.client.close)
                self.client = None
                logging.info("MinIO连接已关闭")
        except Exception as e:
            logging.error(f"关闭MinIO连接失败: {e}") 

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
                    logging.warning("MinIO连接不健康，重新连接")
                    async with self._connection_lock:
                        await self._connect()  # 重新连接
            except Exception as e:
                logging.warning(f"MinIO连接健康检查失败: {e}，重新连接")
                async with self._connection_lock:
                    await self._connect()  # 重新连接
            self._last_health_check = time.time()

    async def _connect(self):
        """
        建立MinIO连接
        """
        # 先关闭现有连接
        if self.client:
            try:
                if hasattr(self.client, 'close'):
                    await asyncio.to_thread(self.client.close)
            except:
                pass
            self.client = None
        
        # 重新创建连接
        for attempt in range(ATTEMPT_TIME):   
            try:        
                # 创建MinIO客户端
                self.client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure
                )

                # 测试连接
                if await self._health_check():
                    logging.info(f"Connected to MinIO {self.endpoint}")
                    return  # 连接成功，直接返回
                else:
                    logging.warning(f"MinIO {self.endpoint} 连接失败，等待重试...")
            
            except asyncio.CancelledError:
                logging.error(f"MinIO连接被取消: {self.endpoint}")
                raise
            except Exception as e:
                logging.warning(f"MinIO {self.endpoint} 连接异常: {e}")

            if attempt < ATTEMPT_TIME - 1:  # 不是最后一次尝试
                await asyncio.sleep(RETRY_DELAY)
        
        # 如果所有重试都失败了
        msg = f"MinIO {self.endpoint} 连接失败，已尝试 {ATTEMPT_TIME} 次"
        logging.error(msg)
        raise ConnectionError(msg)

    def _should_check_health(self) -> bool:
        """判断是否需要健康检查"""
        return time.time() - self._last_health_check > self._health_check_interval

    async def _health_check(self) -> bool:
        """内部健康检查方法"""
        try:
            if self.client:
                await asyncio.to_thread(self.client.list_buckets)
                return True
            return False
        except Exception:
            return False

    def _get_bucket_name(self, bucket_name: Optional[str]) -> str:
        """获取存储桶名称，如果为None则使用默认值"""
        return bucket_name or self.default_bucket_name

    async def _ensure_bucket_exists(self, bucket_name: str):
        """确保存储桶存在"""
        await self._ensure_connect()
        
        try:
            bucket_exists = await asyncio.to_thread(self.client.bucket_exists, bucket_name)
            if not bucket_exists:
                await asyncio.to_thread(self.client.make_bucket, bucket_name)
                logging.info(f"创建MinIO存储桶: {bucket_name}")
            else:
                logging.debug(f"MinIO存储桶已存在: {bucket_name}")
        except Exception as e:
            logging.error(f"MinIO存储桶操作失败: {e}")
            raise