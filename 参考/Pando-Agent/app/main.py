import asyncio
import logging
import uvicorn
from datetime import datetime
from typing import Any
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from app.agents.sessions import models as _agent_session_models
from app.logger import set_log_level, setup_logging
from app.config.settings import settings, APP_NAME, APP_VERSION, APP_DESCRIPTION
from app.middleware.logging import logging_middleware
from app.infrastructure.storage import STORAGE_CONN
from app.infrastructure.vector_store import VECTOR_STORE_CONN
from app.infrastructure.redis import REDIS_CONN
from app.utils.auth.jwt_middleware import create_jwt_middleware
from app.infrastructure.celery.app import celery_app
from app.infrastructure.database import Base, close_db, get_db_session, health_check_db
from app.agents.bus.queues import start_message_gateway, stop_message_gateway
from app.agents.mcp.pool import MCP_POOL
from app.agents.tools.exec.process_manager import PROCESS_MANAGER
from app.channel.websocket.websocket import router as websocket_router
from app.services.cron.manager import start_cron, stop_cron
from app.agents.api.agents import router as agents_config_router
from app.agents.api.skills import router as agent_skills_router
from app.agents.api.skills_hub import router as skills_hub_router
from app.agents.sessions.api import router as sessions_router
from app.infrastructure.llms.api import router as llms_router
from app.services.market import get_market_service


# 创建FastAPI应用
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "deepLinking": True,
        "displayRequestDuration": True,
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
    }
)

# 确保日志配置在应用启动时被正确设置
setup_logging()

#==================================
# 注册所有路由器
#==================================
app.include_router(llms_router, prefix="/api/v1", tags=["模型管理"])
app.include_router(agents_config_router, prefix="/api/v1/agents", tags=["Agent 配置管理"])
app.include_router(agent_skills_router, prefix="/api/v1/agents", tags=["Agent Skill 管理"])
app.include_router(skills_hub_router, prefix="/api/v1/skills", tags=["Skills Hub"])
app.include_router(sessions_router, prefix="/api/v1", tags=["Agent 会话管理"])
app.include_router(websocket_router, prefix="/api/v1", tags=["WebSocket Channel"])
#==================================
# 配置中间件
#==================================
# 配置CORS中间件 - 直接使用FastAPI内置的CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 生产环境应该指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置日志中间件 - 直接使用全局中间件实例
app.add_middleware(logging_middleware)

# 添加JWT中间件到应用（需时取消注释）
# app.middleware("http")(create_jwt_middleware())

def run_celery_worker():
    """在独立线程中运行 Celery Worker"""
    try:
        # 在debug模式下使用debug日志级别，否则使用info
        log_level = 'debug' if settings.debug else 'info'
        celery_app.worker_main(['worker', f'--loglevel={log_level}', '--concurrency=1', '-Q', 'document,default'])
    except Exception as e:
        logging.error(f"Celery Worker 启动失败: {e}")

#==================================
# 初始化基础设施
#==================================
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    try:
        logging.info("开始应用启动流程...")

        if settings.database_type.lower() == "sqlite":
            async with get_db_session() as session:
                conn = await session.connection()
                await conn.run_sync(Base.metadata.create_all)
            logging.info("SQLite 表结构检查完成")

        start_message_gateway()
        
        if settings.enable_cron:
            start_cron()
            logging.info("Cron 调度已启动")

        MCP_POOL.start_idle_cleanup()
        PROCESS_MANAGER.start_prune_loop()

        logging.info(f"{APP_NAME} v{APP_VERSION} 启动成功")

    except Exception as e:
        logging.error(f"应用启动失败: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    await stop_message_gateway()

    if settings.enable_cron:
        await stop_cron()
        logging.info("Cron 调度已停止")

    MCP_POOL.stop_idle_cleanup()
    await PROCESS_MANAGER.shutdown()

    try:
        # 关闭数据库连接
        await close_db()
        
        # 关闭存储连接
        if STORAGE_CONN and hasattr(STORAGE_CONN, 'close'):
            try:
                await STORAGE_CONN.close()
            except Exception as e:
                logging.warning(f"关闭存储连接时出错: {e}")
        logging.info("存储连接已关闭")

        # 关闭向量存储连接
        if VECTOR_STORE_CONN and hasattr(VECTOR_STORE_CONN, 'close'):
            try:
                await VECTOR_STORE_CONN.close()
            except Exception as e:
                logging.warning(f"关闭向量存储连接时出错: {e}")
        logging.info("向量存储连接已关闭")

        # 关闭Redis连接
        if REDIS_CONN and hasattr(REDIS_CONN, 'close'):
            try:
                await REDIS_CONN.close()
            except Exception as e:
                logging.warning(f"关闭Redis连接时出错: {e}")
        logging.info("Redis连接已关闭")
        
    except Exception as e:
        logging.error(f"关闭连接失败: {e}")
    
    logging.info("应用正在关闭...")

# 根路径
@app.get("/")
async def root():
    """根路径 - 服务信息"""
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "docs": "/docs",
        "health": "/health",
        "market_health": "/health/market",
        "market_metrics": "/metrics/market",
        "api_base": "/api/v1"
    }

# 健康检查
_HEALTH_PROBE_TIMEOUT_SEC = 5.0


async def _probe_health(name: str, coro, *, timeout: float = _HEALTH_PROBE_TIMEOUT_SEC) -> bool:
    try:
        return bool(await asyncio.wait_for(coro, timeout=timeout))
    except Exception as exc:
        logging.warning("%s health check failed or timed out: %s", name, exc)
        return False


@app.get("/health")
async def health_check():
    """健康检查接口（轻量探活，不阻塞业务 API）。"""
    try:
        health_status = {
            "status": "healthy",
            "service": APP_NAME,
            "version": APP_VERSION,
            "timestamp": datetime.now().isoformat(),
            "environment": "development" if settings.debug else "production",
            "market_health": "/health/market",
        }

        probes: list[tuple[str, Any]] = [("database", health_check_db())]
        if STORAGE_CONN and hasattr(STORAGE_CONN, "health_check"):
            probes.append(("storage", STORAGE_CONN.health_check()))
        if VECTOR_STORE_CONN and hasattr(VECTOR_STORE_CONN, "health_check"):
            probes.append(("vector_store", VECTOR_STORE_CONN.health_check()))
        if REDIS_CONN and hasattr(REDIS_CONN, "health_check"):
            probes.append(("redis", REDIS_CONN.health_check()))

        results = await asyncio.gather(
            *(_probe_health(name, coro) for name, coro in probes),
            return_exceptions=False,
        )
        unhealthy = False
        for (name, _), ok in zip(probes, results):
            health_status[name] = "healthy" if ok else "unhealthy"
            if not ok:
                unhealthy = True

        if unhealthy:
            health_status["status"] = "unhealthy"

        return health_status

    except Exception as e:
        logging.error(f"健康检查失败: {e}")
        raise HTTPException(status_code=500, detail="服务不健康")

@app.get("/health/market")
async def market_health_check():
    """市场数据服务探活（运维/部署）。"""
    try:
        payload = await get_market_service().check_health()
        status_code = 200 if payload.get("status") != "unhealthy" else 503
        return JSONResponse(content=payload, status_code=status_code)
    except Exception as exc:
        logging.error("market health check failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)[:240])

@app.get("/metrics/market")
async def market_metrics():
    """Market 服务 Prometheus 指标（运维监控）。"""
    if not settings.market_metrics_enabled:
        raise HTTPException(status_code=404, detail="market metrics disabled")
    from app.services.market.metrics import render_prometheus

    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8")

@app.post("/log-level")
async def change_log_level(level: str = Query(..., description="日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL")):
    """动态设置日志级别"""
    try:
        set_log_level(level)
        current_level = logging.getLevelName(logging.getLogger().getEffectiveLevel())
        return {
            "message": f"日志级别已设置为 {level.upper()}",
            "current_level": current_level
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/log-level")
async def get_log_level():
    """获取当前日志级别"""
    current_level = logging.getLevelName(logging.getLogger().getEffectiveLevel())
    return {
        "current_level": current_level
    }

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logging.error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务器错误"}
    )

def main():
    """主函数，用于启动服务器"""
    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug
    )

if __name__ == "__main__":
    main() 