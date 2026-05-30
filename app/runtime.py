import logging
from app.config.settings import APP_NAME, APP_VERSION
from app.infrastructure.database import close_db
from app.infrastructure.database.migrate import upgrade_head
from app.infrastructure.vector_store import VECTOR_STORE_CONN
from app.code_analysis.services.file_analysis_service import FileAnalysisService
from app.code_analysis.services.lsp.lsp_service import CodeLSPService
from app.logger import setup_logging

_runtime_started = False


async def startup(start_scheduler: bool = False) -> None:
    global _runtime_started
    setup_logging()
    if _runtime_started:
        if start_scheduler:
            FileAnalysisService.start_global_scheduler()
        return
    upgrade_head()
    if start_scheduler:
        FileAnalysisService.start_global_scheduler()
    _runtime_started = True
    logging.info("%s v%s 运行环境已就绪", APP_NAME, APP_VERSION)


async def shutdown() -> None:
    global _runtime_started
    await FileAnalysisService.stop_global_scheduler()
    await CodeLSPService.close_all()
    if VECTOR_STORE_CONN and hasattr(VECTOR_STORE_CONN, "close"):
        try:
            await VECTOR_STORE_CONN.close()
        except Exception as e:
            logging.warning("关闭向量存储连接时出错: %s", e)
    await close_db()
    _runtime_started = False
