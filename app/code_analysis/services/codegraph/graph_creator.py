import logging
import os
from typing import List
from app.config.settings import settings
from app.utils.common import local_now_iso, normalize_path
from ..codeast.ast_analyzer import FileAstAnalyzer,FolderAstAnalyzer
from .neo4j_service import Neo4jService


class CodeGraphGenerator:
    def __init__(self, repo_id: str, repo_name: str, repo_local_path: str):
        """初始化代码图谱生成器"""
        self.repo_id = repo_id
        self.repo_name = repo_name
        self.repo_local_path = repo_local_path
        
        self.db_client = Neo4jService(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password
        )

    def close(self) -> None:
        if self.db_client:
            self.db_client.close()

    async def delete_repo_graph(self) -> None:
        self.db_client.delete_repo_nodes(self.repo_id)

    async def delete_file_graph(self, rel_file_path: str) -> None:
        self.db_client.delete_file_nodes(self.repo_id, normalize_path(rel_file_path))

    async def generate_graph(self, clean_stale: bool = False):
        """生成或更新完整的代码知识图谱"""
        start_time = local_now_iso()

        # 创建或更新项目节点
        self.db_client.save_project(
            self.repo_id,
            self.repo_name,
            self.repo_local_path
        )
        
        # 从项目根目录开始分析
        code_folder_analyzer = FolderAstAnalyzer(self.repo_local_path, self.repo_local_path)
        root_folder = await code_folder_analyzer.analyze_folder()
        
        # 保存文件夹结构
        self.db_client.save_folder_node(self.repo_id, root_folder)
        
        # 清理过期节点
        if clean_stale:
            self.db_client.delete_stale_nodes(self.repo_id, start_time)
        
        return root_folder

    async def update_files(self, file_paths: List[str]):
        """增量更新指定文件
        
        处理流程：
        1. 删除每个文件相关的所有节点（函数、类、方法等）
        2. 重新分析文件生成新的节点
        3. 保存新的节点到图谱
        
        Args:
            file_paths: 需要更新的文件路径列表
        """
        for file_path in file_paths:
            if not os.path.isfile(file_path):
                continue
            
            # 转换为相对路径（与保存时一致）
            rel_path = normalize_path(os.path.relpath(file_path, self.repo_local_path))
            
            try:
                # 1. 删除文件相关的所有节点
                self.db_client.delete_file_nodes(self.repo_id, rel_path)

                # 2. 重新分析文件
                file_ast_analyzer = FileAstAnalyzer(self.repo_local_path, file_path)
                file_node = await file_ast_analyzer.analyze_file()
                
                # 3. 保存新的节点
                if file_node:
                    self.db_client.save_file_node(self.repo_id, file_node)
            except Exception as e:
                # 记录错误但继续处理其他文件
                logging.error(f"Error updating file {file_path}: {str(e)}")
                continue

    async def update_folders(self, folder_paths: List[str]):
        """增量更新指定文件夹
        
        处理流程：
        1. 删除每个文件夹相关的所有节点（包括子文件夹、文件、函数、类、方法等）
        2. 重新分析文件夹生成新的节点
        3. 保存新的节点到图谱
        
        Args:
            folder_paths: 需要更新的文件夹路径列表
        """
        for folder_path in folder_paths:
            if not os.path.isdir(folder_path):
                continue
            
            # 转换为相对路径（与保存时一致）
            rel_path = normalize_path(os.path.relpath(folder_path, self.repo_local_path))
            
            try:
                # 1. 删除文件夹相关的所有节点
                self.db_client.delete_folder_nodes(self.repo_id, rel_path)
                
                # 2. 重新分析文件夹
                folder_ast_analyzer = FolderAstAnalyzer(self.repo_local_path, folder_path)
                folder_node = await folder_ast_analyzer.analyze_folder()
                
                # 3. 保存新的节点
                if folder_node:
                    self.db_client.save_folder_node(self.repo_id, folder_node)
            except Exception as e:
                # 记录错误但继续处理其他文件夹
                logging.error(f"Error updating folder {folder_path}: {str(e)}")
                continue