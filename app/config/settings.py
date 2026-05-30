import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings
from app.utils.common import get_project_meta, normalize_path


# 定义全局配置常量
_meta = get_project_meta()
APP_NAME = _meta["name"]
APP_VERSION = _meta["version"]
APP_DESCRIPTION = _meta["description"]
APP_BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DATA_DIR = Path.home() / ".pando"


class Settings(BaseSettings):
    """应用配置类"""

    service_host: str = Field(default="0.0.0.0", description="服务主机地址", env="SERVICE_HOST")
    service_port: int = Field(default=8000, description="服务端口", env="SERVICE_PORT")
    debug: bool = Field(default=False, description="调试模式", env="DEBUG")
    app_log_level: str = Field(default="INFO", description="日志级别", env="APP_LOG_LEVEL")

    # 运行时数据目录    
    runtime_data_dir: str = Field(default=str(DEFAULT_RUNTIME_DATA_DIR), description="运行时数据目录", env="RUNTIME_DATA_DIR")
    
    # 数据库配置
    db_name: str = Field(default="code_analysis_service", description="数据库名称", env="DB_NAME")
    database_type: str = Field(default="sqlite", description="数据库类型: postgresql/mysql/sqlite", env="DATABASE_TYPE")
    db_pool_size: int = Field(default=10, description="连接池大小", env="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, description="最大溢出连接数", env="DB_MAX_OVERFLOW")
    
    # PostgreSQL 配置
    postgresql_host: str = Field(default="localhost", description="PostgreSQL主机地址", env="POSTGRESQL_HOST")
    postgresql_port: int = Field(default=5432, description="PostgreSQL端口", env="POSTGRESQL_PORT")
    postgresql_user: str = Field(default="postgres", description="PostgreSQL用户名", env="POSTGRESQL_USER")
    postgresql_password: str = Field(default="your_password", description="PostgreSQL密码", env="POSTGRESQL_PASSWORD")
    
    # MySQL 配置
    mysql_host: str = Field(default="localhost", description="MySQL主机地址", env="MYSQL_HOST")
    mysql_port: int = Field(default=3306, description="MySQL端口", env="MYSQL_PORT")
    mysql_user: str = Field(default="root", description="MySQL用户名", env="MYSQL_USER")
    mysql_password: str = Field(default="your_password", description="MySQL密码", env="MYSQL_PASSWORD")

    # =============================================================================
    # 向量存储配置 - Vector Store
    # =============================================================================
    # 向量存储引擎类型 (elasticsearch, opensearch)
    vector_store_engine: str = Field(default="elasticsearch", description="向量存储引擎类型", env="VECTOR_STORE_ENGINE")
    # 向量存储映射文件名称
    vector_store_mapping: str = Field(default="es_doc_mapping.json", description="向量存储映射文件名称", env="VECTOR_STORE_MAPPING")
    
    # Elasticsearch配置
    es_hosts: str = Field(default="https://localhost:9200", description="Elasticsearch主机地址", env="ES_HOSTS")
    es_username: str = Field(default="elastic", description="Elasticsearch用户名", env="ES_USERNAME")
    es_password: str = Field(default="changeme", description="Elasticsearch密码", env="ES_PASSWORD")
    es_verify_certs: bool = Field(default=False, description="是否校验 ES 服务端证书，本地 HTTPS 自签证书可设为 False", env="ES_VERIFY_CERTS")
    
    # OpenSearch配置
    os_hosts: str = Field(default="http://localhost:9200", description="OpenSearch主机地址", env="OS_HOSTS")
    os_username: str = Field(default="admin", description="OpenSearch用户名", env="OS_USERNAME")
    os_password: str = Field(default="admin", description="OpenSearch密码", env="OS_PASSWORD")

    # =============================================================================
    # 图数据库 / CodeGraph
    # =============================================================================
    code_graph_enabled: bool = Field(default=True, description="是否启用代码依赖图谱（Neo4j CodeGraph）", env="CODE_GRAPH_ENABLED")
    neo4j_uri: str = Field(default="neo4j://localhost:7687", description="图数据库URI", env="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", description="图数据库用户名", env="NEO4J_USER")
    neo4j_password: str = Field(default="neo4jneo4j", description="图数据库密码", env="NEO4J_PASSWORD")
    neo4j_pool_size: int = Field(default=5, description="连接池大小", env="NEO4J_POOL_SIZE")
    neo4j_max_overflow: int = Field(default=10, description="最大溢出连接数", env="NEO4J_MAX_OVERFLOW")


    # =============================================================================
    # 模型配置说明 见：app/config/xxx.json
    # =============================================================================
    model_cache_dir: str = Field(default="model_cache_dir", description="模型缓存目录(相对 APP_BASE_DIR)", env="MODEL_CACHE_DIR")
    model_temp_dir: str = Field(default="model_temp_dir", description="模型临时目录(相对 runtime_data_dir)", env="MODEL_TEMP_DIR")


    # =============================================================================
    # 代码仓分析 - 行切片（codechunk/code_chunk）
    # =============================================================================
    lsp_enabled: bool = Field(default=True, description="是否启用内置 LSP 客户端", env="LSP_ENABLED")
    code_analysis_line_chunk_target_lines: int = Field(default=5, description="行切片目标窗口行数", env="CODE_ANALYSIS_LINE_CHUNK_TARGET_LINES")
    code_analysis_line_chunk_overlap_lines: int = Field(default=1, description="行切片滑动重叠行数", env="CODE_ANALYSIS_LINE_CHUNK_OVERLAP_LINES")
    code_analysis_line_chunk_max_lines: int = Field(default=200, description="单行切片经扩展后的最大行数上限", env="CODE_ANALYSIS_LINE_CHUNK_MAX_LINES")
    code_analysis_symbol_summary_llm_concurrency: int = Field(default=4, ge=1, le=32, description="符号摘要阶段 LLM 并发上限", env="CODE_ANALYSIS_SYMBOL_SUMMARY_LLM_CONCURRENCY")

    repo_storage_path: str = Field(default="./data/repos", description="远程克隆/上传仓库的本地存储根目录", env="REPO_STORAGE_PATH")
    enable_incremental_scan: bool = Field(default=True, description="是否启用定时增量扫描", env="ENABLE_INCREMENTAL_SCAN")
    incremental_scan_interval_sec: int = Field(default=300, ge=30, description="增量扫描间隔（秒）", env="INCREMENTAL_SCAN_INTERVAL_SEC")

    class Config:
        env_file = "env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def database_url(self) -> str:
        """生成数据库连接URL"""
        if self.database_type.lower() == "postgresql":
            return f"postgresql+asyncpg://{self.postgresql_user}:{self.postgresql_password}@{self.postgresql_host}:{self.postgresql_port}/{self.db_name}"
        elif self.database_type.lower() == "mysql":
            return f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.db_name}"
        else:
            filename = self.db_name if self.db_name.lower().endswith(".db") else f"{self.db_name}.db"
            raw_path = str(Path(self.runtime_data_dir) / "sqlite" / filename)
            abs_path = os.path.abspath(raw_path)
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and not os.path.isdir(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            norm_path = normalize_path(abs_path)
            return f"sqlite+aiosqlite:///{norm_path}"

    @property
    def app_name(self) -> str:
        """应用名称(用于JWT issuer等)"""
        return APP_NAME


# 全局配置实例
settings = Settings() 


# 全局配置常量
MODELS_CONFIG_DIR = Path(settings.runtime_data_dir) / "models"