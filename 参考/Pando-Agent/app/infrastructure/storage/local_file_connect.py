import json
import os
from datetime import datetime
from typing import Optional, BinaryIO, Dict, Any
import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from app.infrastructure.storage.base import StorageBase
from app.config.settings import APP_NAME

class LocalStorage(StorageBase):
    """本地文件存储实现"""
    
    def __init__(self, upload_dir: str):
        """
        初始化本地存储
        
        Args:
            upload_dir: 上传目录路径
        """
        # 确保上传目录存在
        self.upload_dir = Path(upload_dir)        
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        self.default_bucket_name = APP_NAME.lower().replace("_", "-")
        
        logging.info(f"本地存储初始化完成: {self.upload_dir}")
    
    def _save_file_sync(self, file_path: Path, file_data: BinaryIO):
        """同步保存文件"""
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file_data, f)
    
    def _save_metadata_sync(self, metadata_file: Path, file_metadata: Dict[str, Any]):
        """同步保存元数据文件"""
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(file_metadata, f, ensure_ascii=False, indent=2)
    
    def _load_metadata_sync(self, metadata_file: Path) -> Dict[str, Any]:
        """同步加载元数据文件"""
        with open(metadata_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _get_bucket_name(self, bucket_name: Optional[str]) -> str:
        """获取bucket名称"""
        return bucket_name or self.default_bucket_name

    async def put(self, file_index: str, file_data: BinaryIO, 
                  bucket_name: Optional[str] = None,
                  content_type: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> str:
        """上传文件到本地存储"""
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 创建bucket目录（如果不存在）
            bucket_dir = self.upload_dir / bucket_name
            bucket_dir.mkdir(parents=True, exist_ok=True)
            
            # 文件路径（直接使用file_index作为文件名）
            file_path = bucket_dir / file_index
            
            # 保存文件
            await asyncio.to_thread(self._save_file_sync, file_path, file_data)
            
            # 保存元数据到单独的文件（可选，用于保持一致性）
            metadata_file = bucket_dir / f"{file_index}.meta"
            file_metadata = {
                'file_index': file_index,
                'content_type': content_type or "application/octet-stream",
                'upload_time': datetime.now().isoformat()
            }
            
            # 合并自定义元数据
            if metadata:
                file_metadata.update(metadata)
            
            # 保存元数据文件
            await asyncio.to_thread(self._save_metadata_sync, metadata_file, file_metadata)
            
            logging.info(f"文件上传成功: {bucket_name}/{file_index}")
            return file_index
            
        except Exception as e:
            logging.error(f"文件上传失败: {e}")
            raise
    
    async def get(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[BinaryIO]:
        """下载文件"""
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 构造文件路径
            file_path = self.upload_dir / bucket_name / file_index
            
            if not file_path.exists():
                logging.warning(f"文件不存在: {bucket_name}/{file_index}")
                return None
            
            # 返回文件流
            return await asyncio.to_thread(open, file_path, 'rb')
            
        except Exception as e:
            logging.error(f"下载文件失败: {e}")
            return None
    
    async def delete(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """删除文件"""
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 构造文件路径
            file_path = self.upload_dir / bucket_name / file_index
            metadata_file = self.upload_dir / bucket_name / f"{file_index}.meta"
            
            # 删除文件
            if file_path.exists():
                await asyncio.to_thread(file_path.unlink)
            
            # 删除元数据文件
            if metadata_file.exists():
                await asyncio.to_thread(metadata_file.unlink)
            
            logging.info(f"文件删除成功: {bucket_name}/{file_index}")
            return True
            
        except Exception as e:
            logging.error(f"删除文件失败: {e}")
            return False
    
    async def get_url(self, file_index: str, bucket_name: Optional[str] = None, expires_in: Optional[int] = None) -> Optional[str]:
        """获取文件访问URL（本地存储返回文件路径）"""
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 构造文件路径
            file_path = self.upload_dir / bucket_name / file_index
            
            if not file_path.exists():
                logging.warning(f"文件不存在: {bucket_name}/{file_index}")
                return None
            
            # 返回绝对路径作为URL
            return str(file_path.absolute())
            
        except Exception as e:
            logging.error(f"获取文件URL失败: {e}")
            return None
    
    async def exists(self, file_index: str, bucket_name: Optional[str] = None) -> bool:
        """检查文件是否存在"""
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            file_path = self.upload_dir / bucket_name / file_index
            return await asyncio.to_thread(file_path.exists)
        except Exception as e:
            logging.error(f"检查文件存在性失败: {e}")
            return False
    
    async def get_metadata(self, file_index: str, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取文件元数据"""
        try:
            # 使用默认bucket（应用名称）如果没有指定
            bucket_name = self._get_bucket_name(bucket_name)
            
            # 构造文件路径
            file_path = self.upload_dir / bucket_name / file_index
            metadata_file = self.upload_dir / bucket_name / f"{file_index}.meta"
            
            if not file_path.exists():
                logging.warning(f"文件不存在: {bucket_name}/{file_index}")
                return None
            
            # 获取文件基本信息
            stat = file_path.stat()
            
            # 尝试读取元数据文件
            metadata = {}
            if metadata_file.exists():
                try:
                    metadata = await asyncio.to_thread(self._load_metadata_sync, metadata_file)
                except Exception as e:
                    logging.warning(f"读取元数据文件失败: {e}")
            
            return {
                'file_index': file_index,
                'bucket_name': bucket_name,
                'file_size': stat.st_size,
                'last_modified': datetime.fromtimestamp(stat.st_mtime),
                'content_type': metadata.get('content_type', 'application/octet-stream'),
                'metadata': metadata
            }
        except Exception as e:
            logging.error(f"获取文件元数据失败: {e}")
            return None
            
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查上传目录是否可写
            test_file = self.upload_dir / "health_check_test"
            await asyncio.to_thread(test_file.write_text, "health check")
            await asyncio.to_thread(test_file.unlink)
            return True
        except Exception as e:
            logging.error(f"本地存储健康检查失败: {e}")
            return False
    
    async def close(self):
        """关闭连接"""
        try:
            # 本地存储通常不需要显式关闭，但可以清理资源
            logging.info("本地存储连接已关闭")
        except Exception as e:
            logging.error(f"关闭本地存储连接失败: {e}")