import logging
import os
from typing import Dict, List, Optional, Type
from dataclasses import dataclass, asdict
from datetime import datetime
import traceback
from app.utils.common import normalize_path
from .analyzers.python_analyzer import PythonAnalyzer
from .analyzers.java_analyzer import JavaAnalyzer
from .analyzers.go_analyzer import GoAnalyzer
from .analyzers.cpp_analyzer import CppAnalyzer
from .analyzers.c_analyzer import CAnalyzer
from .analyzers.js_analyzer import JsAnalyzer
from .analyzers.base import LanguageAnalyzer
from .model import FileInfo, FolderInfo, Language

_ANALYZER_BY_LANG: Dict[Language, Type[LanguageAnalyzer]] = {
    Language.PYTHON: PythonAnalyzer,
    Language.JAVA: JavaAnalyzer,
    Language.GO: GoAnalyzer,
    Language.CPP: CppAnalyzer,
    Language.C: CAnalyzer,
    Language.JAVASCRIPT: JsAnalyzer,
}


class FileAstAnalyzer:

    def __init__(self, base_path: str, file_path: str):
        """初始化代码图谱生成器"""
        self.base_path = base_path
        self.file_path = file_path
    
    def _detect_language(self) -> Language:
        """根据文件扩展名检测编程语言"""
        ext = os.path.splitext(self.file_path)[1].lower()
        ext_map = {
            '.py': Language.PYTHON,
            '.java': Language.JAVA,
            '.go': Language.GO,
            '.cpp': Language.CPP,
            '.c': Language.C,
            '.js': Language.JAVASCRIPT,
            '.jsx': Language.JAVASCRIPT,
            '.mjs': Language.JAVASCRIPT,
            '.cjs': Language.JAVASCRIPT,
        }
        return ext_map.get(ext, Language.UNKNOWN)
    
    async def analyze_file(self, source: Optional[str] = None) -> Optional[FileInfo]:
        """分析文件；source 为已读入的源码时跳过一次磁盘读取（与切片共用）。
        Returns:
            FileNode: 文件节点
            
        """
        try:
            language = self._detect_language()
            if language == Language.UNKNOWN:
                return None
            analyzer_class = _ANALYZER_BY_LANG.get(language)
            if not analyzer_class:
                return None
            analyzer = analyzer_class(self.base_path, self.file_path)
            return await analyzer.analyze_file(source)
            
        except Exception as e:
            logging.error(f"Error in analyze_file: {str(e)}, file_path: {self.file_path}")
            logging.error(f"Error type: {type(e)}")
            logging.error(f"Stack trace: ", traceback.format_exc())
            return None
    
class FolderAstAnalyzer:
    # 定义需要排除的文件夹
    EXCLUDED_DIRS = {
        '__pycache__',
        '.git',
        '.idea',
        '.vscode',
        'venv',
        'node_modules',
        'dist',
        'build',
        'target',
        '.pytest_cache',
        '.mypy_cache',
        '.coverage',
        '__tests__',
        'tests'
    }

    def __init__(self, base_path: str, folder_path: str):
        """初始化文件夹分析器"""
        self.base_path = base_path
        self.folder_path = folder_path
    
    async def analyze_folder(self, folder_path: str = None, is_subfolder: bool = False) -> FolderInfo:
        """分析文件夹
        Args:
            folder_path: 文件夹绝对路径
            is_subfolder: 是否是子文件夹
            
        Returns:
            FolderNode: 文件夹节点
        """
        if not folder_path:
            folder_path = self.folder_path

        files = []
        subfolders = []        
        for item in os.listdir(folder_path):
            # 跳过隐藏文件和特殊目录
            if item.startswith('.') or item in self.EXCLUDED_DIRS:
                continue
            # 拼接绝对路径
            item_path = os.path.join(folder_path, item)

            try:
                if os.path.isfile(item_path) and item_path.endswith(
                    ('.py', '.java', '.go', '.cpp', '.c', '.js', '.jsx', '.mjs', '.cjs')
                ) and not item_path.startswith('__'):
                    # 分析所有支持的文件类型
                    file_ast_analyzer = FileAstAnalyzer(self.base_path, item_path)
                    file_info = await file_ast_analyzer.analyze_file()
                    if file_info:
                        files.append(file_info)
                elif os.path.isdir(item_path):
                    subfolder_info = await self.analyze_folder(item_path, is_subfolder=True)
                    if subfolder_info:
                        subfolders.append(subfolder_info)
            except Exception as e: # 只记录错误，不抛出异常
                logging.error(f"Error in analyze_folder: {str(e)}, item_path: {item_path}")
                continue

        return FolderInfo(
            name=os.path.basename(folder_path.rstrip(os.sep)),
            path=normalize_path(os.path.relpath(folder_path, self.base_path)),
            files=files,
            subfolders=subfolders
        )
            
        

