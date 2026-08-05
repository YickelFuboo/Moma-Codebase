"""MomaCodeBase MCP Server（stdio）：对外暴露查询工具。"""
import logging
import sys
from typing import Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from MCP.services.query_service import McpQueryService


class McpServer:
    """MCP Server 静态门面：构建 FastMCP 实例并注册查询工具。"""

    NAME = "mcb"
    TOOL_NAMES = (
        "doctor",
        "repo_list",
        "resolve",
        "similar",
        "related",
        "pattern",
        "api",
        "dependents",
        "dependencies",
        "callers",
        "callees",
    )

    _app: Optional[FastMCP] = None

    @classmethod
    def build(cls) -> FastMCP:
        if cls._app is not None:
            return cls._app

        # stdio 协议占用 stdout，日志一律走 stderr
        logging.basicConfig(
            level=logging.WARNING,
            stream=sys.stderr,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

        app = FastMCP(cls.NAME)
        svc = McpQueryService

        @app.tool()
        def doctor() -> Dict[str, object]:
            """环境自检：runtime / DB / 向量库 / CodeGraph / embedding / 已登记仓。"""
            return svc.doctor()

        @app.tool()
        def repo_list() -> Dict[str, object]:
            """列出已登记的本地代码仓（path / kind / name）。"""
            return svc.repo_list()

        @app.tool()
        def resolve(
            path: str,
            query_text: str,
            intent: str = "auto",
            top_k: int = 10,
            timeout_ms: int = 60000,
            with_content: bool = True,
        ) -> Dict[str, object]:
            """主检索：自然语言或代码片段定位相关文件/符号（推荐优先调用）。

            Args:
                path: 已登记仓路径，或上级目录前缀（展开子仓）
                query_text: 用户问题或代码片段
                intent: auto|similar|related|locate|pattern|experience|api|graph
                top_k: 融合结果条数
                timeout_ms: 超时毫秒；0 表示不限制
                with_content: 是否附带源码 snippet
            """
            return svc.resolve(
                path,
                query_text,
                intent=intent,
                top_k=top_k,
                timeout_ms=timeout_ms,
                with_content=with_content,
            )

        @app.tool()
        def similar(
            path: str,
            code: str,
            top_k: int = 10,
            timeout_ms: int = 60000,
            with_content: bool = True,
        ) -> Dict[str, object]:
            """相似代码片段检索（行块向量；仅 kind=code）。"""
            return svc.similar(
                path,
                code,
                top_k=top_k,
                timeout_ms=timeout_ms,
                with_content=with_content,
            )

        @app.tool()
        def related(
            path: str,
            keywords: str,
            top_k: int = 10,
            timeout_ms: int = 60000,
        ) -> Dict[str, object]:
            """相关定位：关键词/符号名（逗号分隔；仅 kind=code）。"""
            return svc.related(
                path,
                keywords,
                top_k=top_k,
                timeout_ms=timeout_ms,
            )

        @app.tool()
        def pattern(
            path: str,
            query_text: str,
            top_k: int = 10,
            timeout_ms: int = 60000,
        ) -> Dict[str, object]:
            """历史开发经验模式检索（仅 kind=code）。"""
            return svc.pattern(
                path,
                query_text,
                top_k=top_k,
                timeout_ms=timeout_ms,
            )

        @app.tool()
        def api(
            path: str,
            query_text: str,
            top_k: int = 10,
            timeout_ms: int = 60000,
        ) -> Dict[str, object]:
            """Lib 公开 API 检索（仅 kind=lib）。"""
            return svc.api(
                path,
                query_text,
                top_k=top_k,
                timeout_ms=timeout_ms,
            )

        @app.tool()
        def dependents(
            path: str,
            file_path: str,
            timeout_ms: int = 60000,
        ) -> Dict[str, object]:
            """查询依赖指定文件的其它文件（须精确到单仓；仅 kind=code）。"""
            return svc.dependents(path, file_path, timeout_ms=timeout_ms)

        @app.tool()
        def dependencies(
            path: str,
            file_path: str,
            timeout_ms: int = 60000,
        ) -> Dict[str, object]:
            """查询指定文件依赖的其它文件（须精确到单仓；仅 kind=code）。"""
            return svc.dependencies(path, file_path, timeout_ms=timeout_ms)

        @app.tool()
        def callers(
            path: str,
            symbol: str,
            limit: int = 20,
            timeout_ms: int = 60000,
        ) -> Dict[str, object]:
            """查询调用指定符号的函数/方法（仅 kind=code）。"""
            return svc.callers(
                path,
                symbol,
                limit=limit,
                timeout_ms=timeout_ms,
            )

        @app.tool()
        def callees(
            path: str,
            symbol: str,
            limit: int = 20,
            timeout_ms: int = 60000,
        ) -> Dict[str, object]:
            """查询指定符号调用的函数/方法（仅 kind=code）。"""
            return svc.callees(
                path,
                symbol,
                limit=limit,
                timeout_ms=timeout_ms,
            )

        cls._app = app
        return app

    @classmethod
    def tool_names(cls) -> List[str]:
        return list(cls.TOOL_NAMES)

    @classmethod
    def run(cls, *, transport: str = "stdio") -> None:
        """启动 MCP Server（默认 stdio，供 Cursor 拉起）。"""
        app = cls.build()
        app.run(transport=transport)


def main() -> None:
    McpServer.run()


if __name__ == "__main__":
    main()
