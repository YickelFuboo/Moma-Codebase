import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, BinaryIO, Dict, Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from app.config.settings import APP_NAME
from app.infrastructure.storage.base import StorageBase

# 常量定义
ATTEMPT_TIME = 3
RETRY_DELAY = 1

class S3Storage(StorageBase):
    """S3存储实现"""
    
    def __init__(self, endpoint_url: str = None, region: str = None, access_key_id: str = None,
                 secret_access_key: str = None, use_ssl: bool = True, 
                 signature_version: str = "s3v4", addressing_style: str = "auto", 
                 prefix_path: str = ""):
        """
        初始化S3存储
        
        Args:
            endpoint_url: 端点URL
            region: 区域
            access_key_id: 访问密钥ID
            secret_access_key: 秘密访问密钥
            use_ssl: 是否使用SSL
            signature_version: 签名版本
            addressing_style: 寻址样式
            prefix_path: 前缀路径
        """
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url
        self.use_ssl = use_ssl
        self.signature_version = signature_version
        self.addressing_style = addressing_style
        self.prefix_path = prefix_path
        self.default_bucket_name = APP_NAME.lower().replace("_", "-")
        
        self.client = None
        self._last_health_check: float = 0
        self._health_check_interval: int = 30
        self._connection_lock = asyncio.Lock()

        logging.info(f"S3存储初始化完成: {endpoint_url}")
    
    async def put(self, file_index: str, file_data: BinaryIO, 
                  bucket_name: Optional[str] = None,
                  content_type: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> str:
        """上传文件到S3"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 确保bucket存在
            await self._ensure_bucket_exists(bucket_name)
            
            # 直接使用file_index作为对象键
            object_key = file_index
            
            # 准备metadata
            s3_metadata = {}
            if metadata:
                s3_metadata.update(metadata)
            
            # 上传文件到S3
            await asyncio.to_thread(
                self.client.upload_fileobj,
                file_data,
                bucket_name,
                object_key,
                ExtraArgs={
                    'ContentType': content_type or "application/octet-stream",
                    'Metadata': s3_metadata
                }
            )
            
            logging.info(f"文件上传成功: {bucket_name}/{object_key}")
            return file_index
            
        except Exception as e:
            logging.error(f"文件上传失败: {e}")
            raise
    
    async def get(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[BinaryIO]:
        """从S3下载文件"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 直接使用file_index作为对象键（使用asyncio.to_thread避免阻塞事件循环）
            response = await asyncio.to_thread(
                self.client.get_object,
                Bucket=bucket_name,
                Key=file_index
            )
            
            return response['Body']
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logging.warning(f"文件不存在: {bucket_name}/{file_index}")
                return None
            else:
                logging.error(f"下载文件失败: {e}")
                raise
    
    async def delete(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """删除S3文件"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 直接使用file_index作为对象键（使用asyncio.to_thread避免阻塞事件循环）
            await asyncio.to_thread(
                self.client.delete_object,
                Bucket=bucket_name,
                Key=file_index
            )
            
            logging.info(f"文件删除成功: {bucket_name}/{file_index}")
            return True
            
        except ClientError as e:
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
                self.client.generate_presigned_url,
                'get_object',
                Params={'Bucket': bucket_name, 'Key': file_index},
                ExpiresIn=expires_in or 3600  # 默认1小时
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
            
            await asyncio.to_thread(
                self.client.head_object, Bucket=bucket_name, Key=file_index
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    async def get_metadata(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取文件元数据"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            response = await asyncio.to_thread(
                self.client.head_object, Bucket=bucket_name, Key=file_index
            )
            
            return {
                'file_index': file_index,
                'bucket_name': bucket_name,
                'file_size': response['ContentLength'],
                'last_modified': response['LastModified'],
                'content_type': response['ContentType'],
                'metadata': response.get('Metadata', {})
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
            logging.info("S3连接已关闭")
        except Exception as e:
            logging.error(f"关闭S3连接失败: {e}")
    
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
                    logging.warning("S3连接不健康，重新连接")
                    async with self._connection_lock:
                        await self._connect()  # 重新连接
            except Exception as e:
                logging.warning(f"S3连接健康检查失败: {e}，重新连接")
                async with self._connection_lock:
                    await self._connect()  # 重新连接
            self._last_health_check = time.time()

    async def _connect(self):
        """
        建立S3连接
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
                # 初始化S3客户端
                client_kwargs = {
                    'region_name': self.region,
                    'aws_access_key_id': self.access_key_id,
                    'aws_secret_access_key': self.secret_access_key,
                    'endpoint_url': self.endpoint_url,
                    'use_ssl': self.use_ssl
                }
                
                # 添加高级配置（如果提供）
                if self.signature_version:
                    client_kwargs['config'] = boto3.session.Config(
                        signature_version=self.signature_version,
                        s3={'addressing_style': self.addressing_style}
                    )
                
                self.client = boto3.client('s3', **client_kwargs)

                # 测试连接
                if await self._health_check():
                    logging.info(f"Connected to S3 {self.endpoint_url}")
                    return  # 连接成功，直接返回
                else:
                    logging.warning(f"S3 {self.endpoint_url} 连接失败，等待重试...")
            
            except asyncio.CancelledError:
                logging.error(f"S3连接被取消: {self.endpoint_url}")
                raise
            except Exception as e:
                logging.warning(f"S3 {self.endpoint_url} 连接异常: {e}")

            if attempt < ATTEMPT_TIME - 1:  # 不是最后一次尝试
                await asyncio.sleep(RETRY_DELAY)
        
        # 如果所有重试都失败了
        msg = f"S3 {self.endpoint_url} 连接失败，已尝试 {ATTEMPT_TIME} 次"
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
        except Exception as e:
            logging.error(f"S3健康检查失败: {e}")
            return False
    
    def _get_bucket_name(self, bucket_name: Optional[str]) -> str:
        """获取存储桶名称，如果为None则使用默认值"""
        return bucket_name or self.default_bucket_name
    
    async def _ensure_bucket_exists(self, bucket_name: str):
        """确保存储桶存在"""
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=bucket_name)
            logging.debug(f"S3存储桶已存在: {bucket_name}")
        
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # 存储桶不存在，创建它
                await asyncio.to_thread(
                    self.client.create_bucket,
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )
                logging.info(f"创建S3存储桶: {bucket_name}")
            else:
                raise
    