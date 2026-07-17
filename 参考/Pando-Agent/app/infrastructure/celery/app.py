from celery import Celery
from celery.signals import worker_process_init
import logging
import sys
import os
from app.config.settings import settings
from app.logger import ColoredFormatter

# 创建 Celery 实例
celery_app = Celery('knowledge_service')

# 基本配置
celery_app.conf.update({
    'broker_url': settings.redis_url,
    'result_backend': settings.redis_url,
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'UTC',
    'enable_utc': True,
    'task_track_started': True,
    'task_time_limit': 30 * 60,
    'task_soft_time_limit': 25 * 60,
    'worker_prefetch_multiplier': 1,
    'task_acks_late': True,
    'worker_max_tasks_per_child': 1000,
    'task_routes': {
        'app.tasks.document_tasks.parse_document_task': {'queue': 'document'},
    },
    'task_default_queue': 'default',
    'task_default_exchange': 'default',
    'task_default_routing_key': 'default',
    'task_remote_control': True,
    'worker_disable_rate_limits': False,
    'broker_connection_retry_on_startup': True,
    'worker_pool': 'solo',  # Windows平台使用solo模式避免进程问题
})

# 任务自动发现
celery_app.autodiscover_tasks(packages=[
    'app.tasks',
])

@worker_process_init.connect
def setup_celery_logging(**kwargs):
    """为Celery worker进程设置自定义日志格式"""
    # 直接复用主应用的日志配置
    from app.logger import setup_logging
    
    # 调用主应用的日志设置
    setup_logging()
    
    # 添加Celery标识到日志格式
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
            # 为控制台处理器添加Celery标识
            original_formatter = handler.formatter
            if isinstance(original_formatter, ColoredFormatter):
                class CeleryColoredFormatter(ColoredFormatter):
                    def format(self, record):
                        formatted = super().format(record)
                        return f"[CELERY] {formatted}"
                handler.setFormatter(CeleryColoredFormatter())
    
    logging.info("✅ Celery Worker 日志配置已应用（复用主应用格式）")