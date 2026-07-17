import os
from pathlib import Path
from typing import Optional
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
    """应用配置类 - 平铺结构"""
    
    # 应用基础配置
    service_host: str = Field(default="0.0.0.0", description="服务主机地址", env="SERVICE_HOST")
    service_port: int = Field(default=8000, description="服务端口", env="SERVICE_PORT")
    debug: bool = Field(default=False, description="调试模式", env="DEBUG")
    app_log_level: str = Field(default="INFO", description="日志级别", env="APP_LOG_LEVEL")

    # 运行时数据目录    
    runtime_data_dir: str = Field(default=str(DEFAULT_RUNTIME_DATA_DIR), description="运行时数据目录", env="RUNTIME_DATA_DIR")

    # 认证配置
    auth_user_service_url: str = Field(default="http://localhost:8000", description="User-Service地址", env="AUTH_USER_SERVICE_URL")
    auth_request_timeout: int = Field(default=5, description="请求超时时间(秒)", env="AUTH_REQUEST_TIMEOUT")
    auth_jwks_endpoint: str = Field(default="/.well-known/jwks.json", description="JWKS端点", env="AUTH_JWKS_ENDPOINT")
    auth_jwt_config_endpoint: str = Field(default="/jwt-config", description="JWT配置端点", env="AUTH_JWT_CONFIG_ENDPOINT")
    auth_blacklist_endpoint: str = Field(default="/blacklist", description="黑名单端点", env="AUTH_BLACKLIST_ENDPOINT")
    
    # 数据库配置
    db_name: str = Field(default="knowledge_service", description="数据库名称", env="DB_NAME")
    database_type: str = Field(default="postgresql", description="数据库类型: postgresql/mysql/sqlite", env="DATABASE_TYPE")
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

    # 文件存储配置
    storage_type: str = Field(default="minio", description="存储类型: minio, s3, local", env="STORAGE_TYPE")
    
    # MinIO 配置
    minio_endpoint: str = Field(default="localhost:9000", description="MinIO端点", env="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", description="MinIO访问密钥", env="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", description="MinIO秘密密钥", env="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, description="MinIO是否使用HTTPS", env="MINIO_SECURE")
    
    # S3 配置
    s3_region: str = Field(default="us-east-1", description="S3区域", env="S3_REGION")
    s3_endpoint_url: str = Field(default="https://your-s3-endpoint.com", description="S3端点URL", env="S3_ENDPOINT_URL")
    s3_access_key_id: str = Field(default="your_access_key", description="S3访问密钥ID", env="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="your_secret_key", description="S3秘密访问密钥", env="S3_SECRET_ACCESS_KEY")
    s3_use_ssl: bool = Field(default=True, description="S3是否使用SSL", env="S3_USE_SSL")
    
    # 本地存储配置
    local_upload_dir: str = Field(default="./data/upload_files", description="本地上传目录", env="LOCAL_UPLOAD_DIR")
    
    # Azure Blob Storage SAS配置
    azure_account_url: str = Field(default="https://yourstorageaccount.blob.core.windows.net", description="Azure存储账户URL", env="AZURE_ACCOUNT_URL")
    azure_sas_token: str = Field(default="your_sas_token", description="Azure SAS令牌", env="AZURE_SAS_TOKEN")
    
    # Azure Blob Storage SPN配置
    azure_spn_account_url: str = Field(default="https://yourstorageaccount.dfs.core.windows.net", description="Azure SPN存储账户URL", env="AZURE_SPN_ACCOUNT_URL")
    azure_spn_client_id: str = Field(default="your_client_id", description="Azure SPN客户端ID", env="AZURE_SPN_CLIENT_ID")
    azure_spn_client_secret: str = Field(default="your_client_secret", description="Azure SPN客户端密钥", env="AZURE_SPN_CLIENT_SECRET")
    azure_spn_tenant_id: str = Field(default="your_tenant_id", description="Azure SPN租户ID", env="AZURE_SPN_TENANT_ID")
    azure_spn_container_name: str = Field(default="your_container", description="Azure SPN容器名称", env="AZURE_SPN_CONTAINER_NAME")
    
    # OSS配置
    oss_access_key: str = Field(default="your_access_key", description="OSS访问密钥ID", env="OSS_ACCESS_KEY")
    oss_secret_key: str = Field(default="your_secret_key", description="OSS秘密访问密钥", env="OSS_SECRET_KEY")
    oss_endpoint_url: str = Field(default="https://oss-cn-hangzhou.aliyuncs.com", description="OSS端点URL", env="OSS_ENDPOINT_URL")
    oss_region: str = Field(default="cn-hangzhou", description="OSS区域", env="OSS_REGION")
    oss_prefix_path: str = Field(default="", description="OSS前缀路径", env="OSS_PREFIX_PATH")
    
    # Redis配置
    redis_host: str = Field(default="localhost", description="Redis主机地址", env="REDIS_HOST")
    redis_port: int = Field(default=6379, description="Redis端口", env="REDIS_PORT")
    redis_db: int = Field(default=0, description="Redis数据库编号", env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, description="Redis密码", env="REDIS_PASSWORD")
    redis_ssl: bool = Field(default=False, description="是否使用SSL连接", env="REDIS_SSL")
    redis_decode_responses: bool = Field(default=True, description="是否自动解码响应", env="REDIS_DECODE_RESPONSES")
    redis_socket_connect_timeout: int = Field(default=5, description="连接超时时间(秒)", env="REDIS_SOCKET_CONNECT_TIMEOUT")
    redis_socket_timeout: int = Field(default=5, description="读写超时时间(秒)", env="REDIS_SOCKET_TIMEOUT")
    redis_retry_on_timeout: bool = Field(default=True, description="超时时是否重试", env="REDIS_RETRY_ON_TIMEOUT")
    redis_max_connections: int = Field(default=5, description="每个数据库的最大连接数", env="REDIS_MAX_CONNECTIONS")


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
    # 图数据库配置
    # =============================================================================
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
    # Web 工具配置 - Web Search / Fetch
    # =============================================================================
    tavily_api_key: str = Field(default="", description="Tavily API密钥（搜索与抽取）", env="TAVILY_API_KEY")
    brave_api_key: str = Field(default="", description="Brave搜索API密钥", env="BRAVE_API_KEY")
    serper_api_key: str = Field(default="", description="Serper搜索API密钥", env="SERPER_API_KEY")
    firecrawl_api_key: str = Field(default="", description="Firecrawl API密钥", env="FIRECRAWL_API_KEY")
    jina_api_key: str = Field(default="", description="Jina Reader API密钥（可选，无Key时匿名限流）", env="JINA_API_KEY")
    web_search_primary: str = Field(default="tavily", description="web_search 主选: tavily | brave | serper | duckduckgo", env="WEB_SEARCH_PRIMARY")
    web_search_fallback: str = Field(default="brave", description="web_search 备选；留空表示不回退", env="WEB_SEARCH_FALLBACK")
    web_fetch_primary: str = Field(default="static", description="web_fetch 主选: static | tavily | firecrawl | jina", env="WEB_FETCH_PRIMARY")
    web_fetch_fallback: str = Field(default="tavily", description="web_fetch 备选；留空表示不回退", env="WEB_FETCH_FALLBACK")

    # =============================================================================
    # 市场数据服务
    # =============================================================================
    market_data_provider: str = Field(
        default="auto",
        description="market 数据源: auto | wind | choice | tushare | akshare",
        env="MARKET_DATA_PROVIDER",
    )
    tushare_token: str = Field(default="", description="Tushare Pro Token", env="TUSHARE_TOKEN")
    wind_enabled: bool = Field(default=True, description="auto 模式下是否尝试 Wind 终端", env="WIND_ENABLED")
    choice_username: str = Field(default="", description="东方财富 Choice 账号", env="CHOICE_USERNAME")
    choice_password: str = Field(default="", description="东方财富 Choice 密码", env="CHOICE_PASSWORD")
    choice_activate_code: str = Field(default="", description="Choice SDK 激活码（可选）", env="CHOICE_ACTIVATE_CODE")
    market_retry_count: int = Field(default=3, description="market 请求失败重试次数", env="MARKET_RETRY_COUNT")
    market_retry_delay_sec: float = Field(default=1.0, description="market 重试基础间隔(秒)", env="MARKET_RETRY_DELAY_SEC")
    market_retry_retriable_only: bool = Field(
        default=True,
        description="仅对网络类错误重试；False 时对所有异常重试",
        env="MARKET_RETRY_RETRIABLE_ONLY",
    )
    market_cache_ttl_sec: int = Field(default=300, description="现货/ETF 本地缓存 TTL(秒)", env="MARKET_CACHE_TTL_SEC")
    market_no_proxy: bool = Field(
        default=True,
        description="为 eastmoney 等行情域名追加 NO_PROXY，缓解系统代理导致的 ProxyError",
        env="MARKET_NO_PROXY",
    )
    market_metrics_enabled: bool = Field(
        default=True,
        description="是否记录 market Prometheus 指标",
        env="MARKET_METRICS_ENABLED",
    )

    # =============================================================================
    # Skills Hub
    # =============================================================================
    github_token: str = Field(default="", description="GitHub PAT，Skills Hub 拉取仓库文件", env="GITHUB_TOKEN")
    gh_token: str = Field(default="", description="GitHub PAT 别名", env="GH_TOKEN")

    # =============================================================================
    # Agent配置 - Agent 会话存储
    # =============================================================================
    enable_local_session_storage: bool = Field(default=False, description="为 True 时会话存本地文件，为 False 时存数据库", env="ENABLE_LOCAL_SESSION_STORAGE")
    enable_cron: bool = Field(default=True, description="当前进程是否运行 cron 调度循环；多进程部署时仅在一个进程设为 True，避免重复执行", env="ENABLE_CRON")
    enable_message_interrupt: bool = Field(default=True, description="同一会话新消息是否中断当前Agent，true=中断并优先处理新消息，false=排队等待", env="ENABLE_MESSAGE_INTERRUPT")
    agent_run_hard_kill_grace_sec: int = Field(default=15, description="/stop 软中止后等待协作退出的宽限(秒)，超时则 cancel run；/kill 不使用", env="AGENT_RUN_HARD_KILL_GRACE_SEC")
    enable_tool_result_truncate: bool = Field(default=False, description="工具结果超长保存到文件", env="ENABLE_TOOL_RESULT_TRUNCATE")
    tool_result_truncate_max_lines: int = Field(default=2000, description="工具结果截断最大行数", env="TOOL_RESULT_TRUNCATE_MAX_LINES")
    tool_result_truncate_max_bytes: int = Field(default=51200, description="工具结果截断最大字节数(50KB)", env="TOOL_RESULT_TRUNCATE_MAX_BYTES")
    enable_file_state_guard: bool = Field(default=True, description="跨 Actor 文件读写协调（file_state）", env="ENABLE_FILE_STATE_GUARD")
    max_parallel_tool_workers: int = Field(default=8, description="Agent 单轮可并行执行的工具调用上限", env="MAX_PARALLEL_TOOL_WORKERS")

    # =============================================================================
    # 会话压缩 - Session Compaction
    # =============================================================================
    compaction_auto: bool = Field(default=True, description="上下文溢出时是否自动压缩会话", env="COMPACTION_AUTO")
    compaction_reserved: int = Field(default=20_000, description="为压缩预留的 token 缓冲", env="COMPACTION_RESERVED")
    compaction_context_limit: int = Field(default=128_000, description="模型上下文上限(token)，用于溢出判断", env="COMPACTION_CONTEXT_LIMIT")
    compaction_keep_last_n: int = Field(default=6, description="触发压缩时保留的最近消息条数", env="COMPACTION_KEEP_LAST_N")
    compaction_prune: bool = Field(default=True, description="是否启用旧工具输出修剪(prune)", env="COMPACTION_PRUNE")
    compaction_prune_protect: int = Field(default=40_000, description="保护最近工具输出token窗口(prune)", env="COMPACTION_PRUNE_PROTECT")
    compaction_prune_minimum: int = Field(default=20_000, description="触发修剪的最小待修剪token量(prune)", env="COMPACTION_PRUNE_MINIMUM")
    compaction_prune_protected_tools: str = Field(default="skill", description="不参与修剪的工具名(逗号分隔)", env="COMPACTION_PRUNE_PROTECTED_TOOLS")

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
    def redis_url(self) -> str:
        """生成Redis连接URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def app_name(self) -> str:
        """应用名称(用于JWT issuer等)"""
        return APP_NAME


# 全局配置实例
settings = Settings()


# 全局配置常量
MODELS_CONFIG_DIR = Path(settings.runtime_data_dir) / "models"