import logging
from typing import Optional
from app.config.settings import settings
from app.infrastructure.storage.base import StorageBase
from app.infrastructure.storage.minio_connect import MinIOStorage
from app.infrastructure.storage.s3_connect import S3Storage
from app.infrastructure.storage.local_file_connect import LocalStorage
from app.infrastructure.storage.azure_sas_connect import AzureSasStorage
from app.infrastructure.storage.azure_spn_connect import AzureSpnStorage
from app.infrastructure.storage.oss_connect import OSSStorage


class StorageFactory:
    """存储工厂类"""
    
    def __init__(self):
        self._connection: Optional[StorageBase] = None
        self._connection_type: Optional[str] = None
    
    def create_connection(self, storage_type: str = None) -> StorageBase:
        """
        创建存储连接
        
        Args:
            storage_type: 存储类型，如果为None则从配置读取
        
        Returns:
            StorageBase: 存储连接实例
        """
        # 使用配置中的默认值
        actual_storage_type = storage_type or settings.storage_type
        storage_type_lower = actual_storage_type.lower()
        
        try:
            if storage_type_lower == "s3":
                connection = S3Storage(
                    endpoint_url=settings.s3_endpoint_url,
                    region=settings.s3_region,
                    access_key_id=settings.s3_access_key_id,
                    secret_access_key=settings.s3_secret_access_key,
                    use_ssl=settings.s3_use_ssl,
                    signature_version="s3v4",
                    addressing_style="auto",
                    prefix_path=""
                )
            elif storage_type_lower == "minio":
                connection = MinIOStorage(
                    endpoint=settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_secure
                )
            elif storage_type_lower == "local":
                connection = LocalStorage(
                    upload_dir=settings.local_upload_dir
                )
            elif storage_type_lower == "azure_sas":
                connection = AzureSasStorage(
                    account_url=settings.azure_account_url,
                    sas_token=settings.azure_sas_token
                )
            elif storage_type_lower == "azure_spn":
                connection = AzureSpnStorage(
                    account_url=settings.azure_spn_account_url,
                    client_id=settings.azure_spn_client_id,
                    client_secret=settings.azure_spn_client_secret,
                    tenant_id=settings.azure_spn_tenant_id,
                    container_name=settings.azure_spn_container_name
                )
            elif storage_type_lower == "oss":
                connection = OSSStorage(
                    access_key=settings.oss_access_key,
                    secret_key=settings.oss_secret_key,
                    endpoint_url=settings.oss_endpoint_url,
                    region=settings.oss_region,
                    prefix_path=settings.oss_prefix_path
                )
            else:
                raise ValueError(f"不支持的存储类型: {storage_type_lower}")
            
            # 保存连接信息
            self._connection = connection
            self._connection_type = actual_storage_type
            
            logging.info(f"存储连接创建成功: {actual_storage_type}")
            return connection
            
        except Exception as e:
            logging.error(f"创建存储连接失败: {e}")
            raise
    
# 全局工厂实例
_storage_factory = StorageFactory()

# 全局连接变量 - 使用默认配置创建
STORAGE_CONN = _storage_factory.create_connection()
