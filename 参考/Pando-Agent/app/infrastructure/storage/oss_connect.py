from typing import Optional, BinaryIO, Dict, Any
import logging
import time
import asyncio
from io import BytesIO
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from app.infrastructure.storage.base import StorageBase
from app.config.settings import APP_NAME

# 常量定义
ATTEMPT_TIME = 3
RETRY_DELAY = 1

class OSSStorage(StorageBase):
    """OSS存储实现"""
    
    def __init__(self, access_key: str, secret_key: str, endpoint_url: str, 
                 region: str, prefix_path: str = ""):
        """
        初始化OSS存储
        
        Args:
            access_key: OSS访问密钥ID
            secret_key: OSS秘密访问密钥
            endpoint_url: OSS端点URL
            region: OSS区域
            prefix_path: 前缀路径
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint_url = endpoint_url
        self.region = region
        self.prefix_path = prefix_path
        self.default_bucket_name = APP_NAME.lower().replace("_", "-")

        self.client = None
        self._last_health_check: float = 0
        self._health_check_interval: int = 30
        self._connection_lock = asyncio.Lock()
        
        logging.info("OSS存储初始化完成")
    
    async def put(self, file_index: str, file_data: BinaryIO, 
                  bucket_name: Optional[str] = None,
                  content_type: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> str:
        """上传文件到OSS"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 读取文件数据
            binary_data = file_data.read()
            
            # 获取对象键
            object_key = self._get_object_key(file_index)
            
            # 确保bucket存在
            await self._ensure_bucket_exists(bucket_name)
            
            # 上传文件
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            if metadata:
                extra_args['Metadata'] = metadata
            
            await asyncio.to_thread(
                self.client.upload_fileobj,
                BytesIO(binary_data), 
                bucket_name, 
                object_key,
                ExtraArgs=extra_args
            )
            
            logging.info(f"文件上传成功: {bucket_name}/{object_key}")
            return file_index
            
        except Exception as e:
            logging.error(f"文件上传失败: {e}")
            raise
    
    async def get(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[BinaryIO]:
        """从OSS下载文件"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 获取对象键
            object_key = self._get_object_key(file_index)
            
            response = await asyncio.to_thread(
                self.client.get_object, Bucket=bucket_name, Key=object_key
            )
            object_data = response['Body'].read()
            return BytesIO(object_data)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logging.warning(f"文件不存在: {bucket_name}/{object_key}")
                return None
            else:
                logging.error(f"下载文件失败: {e}")
                raise
        except Exception as e:
            logging.error(f"下载文件失败: {e}")
            return None
    
    async def delete(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """删除OSS文件"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 获取对象键
            object_key = self._get_object_key(file_index)
            
            await asyncio.to_thread(
                self.client.delete_object, Bucket=bucket_name, Key=object_key
            )
            logging.info(f"文件删除成功: {bucket_name}/{object_key}")
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
            
            # 获取对象键
            object_key = self._get_object_key(file_index)
            
            url = await asyncio.to_thread(
                self.client.generate_presigned_url,
                'get_object',
                Params={'Bucket': bucket_name, 'Key': object_key},
                ExpiresIn=expires_in or 3600
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
            
            # 获取对象键
            object_key = self._get_object_key(file_index)
            
            await asyncio.to_thread(
                self.client.head_object, Bucket=bucket_name, Key=object_key
            )
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logging.error(f"检查文件存在性失败: {e}")
                raise
        except Exception as e:
            logging.error(f"检查文件存在性失败: {e}")
            return False
    
    async def get_metadata(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取文件元数据"""
        await self._ensure_connect()
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 获取对象键
            object_key = self._get_object_key(file_index)
            
            response = await asyncio.to_thread(
                self.client.head_object, Bucket=bucket_name, Key=object_key
            )
            
            return {
                'file_index': file_index,
                'bucket_name': bucket_name,
                'object_key': object_key,
                'file_size': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType'),
                'etag': response.get('ETag'),
                'metadata': response.get('Metadata', {})
            }
            
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
            logging.error(f"OSS健康检查失败: {e}")
            return False
    
    async def close(self):
        """关闭连接"""
        try:
            if self.client:
                if hasattr(self.client, 'close'):
                    await asyncio.to_thread(self.client.close)
                self.client = None
            logging.info("OSS连接已关闭")
        except Exception as e:
            logging.error(f"关闭OSS连接失败: {e}")
    
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
                    logging.warning("OSS连接不健康，重新连接")
                    async with self._connection_lock:
                        await self._connect()  # 重新连接
            except Exception as e:
                logging.warning(f"OSS连接健康检查失败: {e}，重新连接")
                async with self._connection_lock:
                    await self._connect()  # 重新连接
            self._last_health_check = time.time()

    async def _connect(self):
        """建立OSS连接"""
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
                # 参考：https://help.aliyun.com/zh/oss/developer-reference/use-amazon-s3-sdks-to-access-oss
                self.client = boto3.client(
                    's3',
                    region_name=self.region,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    endpoint_url=self.endpoint_url,
                    config=Config(s3={"addressing_style": "virtual"}, signature_version='v4')
                )

                # 测试连接
                if await self._health_check():
                    logging.info(f"Connected to OSS {self.endpoint_url}")
                    return  # 连接成功，直接返回
                else:
                    logging.warning(f"OSS {self.endpoint_url} 连接失败，等待重试...")
            
            except asyncio.CancelledError:
                logging.error(f"OSS连接被取消: {self.endpoint_url}")
                raise
            except Exception as e:
                logging.warning(f"OSS {self.endpoint_url} 连接异常: {e}")

            if attempt < ATTEMPT_TIME - 1:  # 不是最后一次尝试
                await asyncio.sleep(RETRY_DELAY)
        
        # 如果所有重试都失败了
        msg = f"OSS {self.endpoint_url} 连接失败，已尝试 {ATTEMPT_TIME} 次"
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
            logging.error(f"OSS健康检查失败: {e}")
            return False

    def _get_bucket_name(self, bucket_name: Optional[str]) -> str:
        """获取存储桶名称，如果为None则使用默认值"""
        return bucket_name or self.default_bucket_name

    def _get_object_key(self, file_index: str) -> str:
        """获取对象键，包含前缀路径"""
        if self.prefix_path:
            return f"{self.prefix_path}/{file_index}"
        return file_index
    
    async def _ensure_bucket_exists(self, bucket_name: str):
        """确保bucket存在"""
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=bucket_name)
            logging.debug(f"OSS存储桶已存在: {bucket_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                # Bucket不存在，创建它
                await asyncio.to_thread(self.client.create_bucket, Bucket=bucket_name)
                logging.info(f"创建OSS存储桶: {bucket_name}")
            else:
                raise
