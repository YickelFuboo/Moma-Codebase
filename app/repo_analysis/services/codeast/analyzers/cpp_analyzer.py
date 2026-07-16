import logging
import os
import re
from typing import List,Optional,Set
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser
from app.utils.common import normalize_path
from .base import LanguageAnalyzer
from ..model import FileInfo, FunctionInfo, ClassInfo, ClassType, FunctionType, Language as Lang

# 全局变量存储已加载的语言
LANGUAGES = {}

def get_language():
    """获取或初始化 C++ 语言解析器"""
    if 'cpp' not in LANGUAGES:
        try:
            cpp_lang = Language(tscpp.language())
            parser = Parser()
            parser.language = cpp_lang
            LANGUAGES['cpp'] = parser
        except Exception as e:
            logging.error(f"Error loading C++ language: {str(e)}")
            return None
    return LANGUAGES['cpp']

class CppAnalyzer(LanguageAnalyzer):
    def __init__(self, base_path: str, file_path: str):
        """初始化C++分析器"""
        super().__init__(base_path, file_path)        
        # 获取解析器
        self.parser = get_language()
    
    async def analyze_file(self, source: Optional[str] = None) -> Optional[FileInfo]:
        """分析C++文件"""    
        if self.parser is None:
            logging.error(f"CPP parser is not initialized")
            return None

        try:
            content = source if source is not None else self._read_source_file()

            tree = self.parser.parse(bytes(content, 'utf8'))
            if not tree:
                return None
                
            functions = []
            classes = []
            
            # 遍历语法树
            cursor = tree.walk()
            
            async def visit_node(node):
                if node.type == 'function_definition':
                    func_name = self._get_function_name(node)
                    if not func_name.startswith('_'):
                        func_node = await self._create_function_node(node, content)
                        if func_node:
                            functions.append(func_node)
                elif node.type == 'class_definition':
                    class_node = await self._create_class_node(node, content)
                    if class_node:
                        classes.append(class_node)
                
                for child in node.children:
                    await visit_node(child)
            
            await visit_node(tree.root_node)

            imports = self.get_imports(content)
            cur_file_rel_path = normalize_path(os.path.relpath(self.file_path, self.base_path))
            dep_paths = self._dependent_files_from_includes(imports, cur_file_rel_path)
            
            return FileInfo(
                name=os.path.basename(self.file_path),
                file_path=cur_file_rel_path,
                language=Lang.CPP,
                functions=functions,
                classes=classes,
                imports=imports,
                dependent_files=dep_paths,
            )
        except Exception as e:
            logging.error(f"Error analyzing C++ file {self.file_path}: {str(e)}")
            return None
    
    def get_imports(self, content: str) -> List[str]:
        """获取C++文件的导入依赖"""
        imports: List[str] = []
        include_pattern = r'#include\s*[<"]([^>"]+)[>"]'
        for match in re.finditer(include_pattern, content):
            imports.append(match.group(1))
        return list(dict.fromkeys(imports))

    def _dependent_files_from_includes(self, includes: List[str], cur_file_rel_path: str) -> List[str]:
        """把 C++ 的 include 映射到本仓库内被依赖文件（低档：文件级静态依赖）。"""
        dependent_files: Set[str] = set()
        cur_dir = os.path.dirname(self.file_path)

        def add_if_inside_repo(abs_path: str) -> bool:
            if not os.path.isfile(abs_path):
                return False
            rel = normalize_path(os.path.relpath(abs_path, self.base_path))
            if rel.startswith("../") or rel == cur_file_rel_path:
                return False
            dependent_files.add(rel)
            return True

        for inc in includes:
            if not inc:
                continue
            inc = inc.strip().replace("\\", "/")
            if not inc:
                continue

            # 本地优先：当前文件目录 -> 仓库根目录
            local_candidate = os.path.normpath(os.path.join(cur_dir, inc.replace("/", os.sep)))
            if add_if_inside_repo(local_candidate):
                continue

            repo_candidate = os.path.normpath(os.path.join(self.base_path, inc.replace("/", os.sep)))
            add_if_inside_repo(repo_candidate)

        return sorted(dependent_files)
        
    def _get_function_name(self, node) -> str:
        """获取函数名"""
        for child in node.children:
            if child.type == 'identifier':
                return child.text.decode('utf8')
        return ''
        
    async def _create_function_node(self, node, content: str) -> Optional[FunctionInfo]:
        """创建函数节点"""
        func_name = self._get_function_name(node)
        if not func_name:
            return None
            
        source_code = content[node.start_byte:node.end_byte]
        
        signature = self._get_function_signature(node, content)
        full_name = func_name  # C++ 函数可能需要命名空间，这里简化处理
        
        return FunctionInfo(
            name=func_name,
            full_name=full_name,
            signature=signature,
            type=FunctionType.FUNCTION.value,
            file_path=normalize_path(os.path.relpath(self.file_path, self.base_path)),
            source_code=source_code,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            params=self._get_function_params(node),
            param_types=self._get_param_types(node),
            returns=self._get_function_returns(node),
            return_types=self._get_return_types(node),
            docstring=self._get_comment(node, content)
        )
        
    async def _create_class_node(self, node, content: str) -> Optional[ClassInfo]:
        """创建类节点"""
        class_name = self._get_class_name(node)
        if not class_name:
            return None
            
        source_code = content[node.start_byte:node.end_byte]
        full_name = class_name  # C++ 类可能需要命名空间，这里简化处理
        
        return ClassInfo(
            name=class_name,
            full_name=full_name,
            file_path=normalize_path(os.path.relpath(self.file_path, self.base_path)),
            node_type=ClassType.CLASS.value,
            source_code=source_code,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            methods=await self._get_class_methods(node, content),
            attributes=self._get_class_attributes(node),
            docstring=self._get_comment(node, content)
        ) 