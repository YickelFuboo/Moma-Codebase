import enum
import uuid
from sqlalchemy import Column,String,Text,ForeignKey,Index,DateTime,func,UniqueConstraint
from app.infrastructure.database import Base


class RepoAnalysisStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FileAnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RepoAnalysisType(str, enum.Enum):
    LINE_CHUNK_VECTOR = "line_chunk_vector"
    SYMBOL_SUMMARY_VECTOR = "symbol_summary_vector"


class RepoAnalysisTask(Base):
    """代码仓级扫描任务状态与分析汇总快照。"""
    __tablename__ = "repo_analysis_tasks"

    repo_id = Column(String(36), ForeignKey("git_repositories.id"), primary_key=True, comment="代码仓ID")
    scan_status = Column(String(32), nullable=False, default=RepoAnalysisStatus.IDLE.value, index=True, comment="扫描任务状态")
    last_error = Column(Text, nullable=True, comment="最近错误")
    last_scan_started_at = Column(DateTime, nullable=True, comment="最近扫描开始时间")
    last_scan_finished_at = Column(DateTime, nullable=True, comment="最近扫描结束时间")
    scan_heartbeat_at = Column(DateTime, nullable=True, comment="扫描任务心跳时间")

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_repo_analysis_task_scan_status", "scan_status"),
    )


class RepoFileAnalysisState(Base):
    """文件级分析状态：每个文件一条记录，分析时跑全量类型。"""
    __tablename__ = "repo_file_analysis_state"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="ID")
    repo_id = Column(String(36), ForeignKey("git_repositories.id"), nullable=False, index=True, comment="代码仓ID")
    file_path = Column(String(500), nullable=False, index=True, comment="相对路径")
    status = Column(String(32), nullable=False, default=FileAnalysisStatus.PENDING.value, index=True, comment="状态")
    last_error = Column(Text, nullable=True, comment="最近错误")
    last_started_at = Column(DateTime, nullable=True, comment="最近开始分析时间")
    last_finished_at = Column(DateTime, nullable=True, comment="最近结束分析时间")

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("repo_id", "file_path", name="uq_repo_file"),
        Index("idx_repo_file_analysis_lookup", "repo_id", "file_path"),
        Index("idx_repo_file_analysis_dispatch", "repo_id", "status"),
    )
