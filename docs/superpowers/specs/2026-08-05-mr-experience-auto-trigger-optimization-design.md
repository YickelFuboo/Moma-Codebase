# MR 经验分析自动触发逻辑优化设计

**日期**: 2026-08-05
**状态**: 设计稿
**关联模块**: `app/repo_analysis/services/incremental_scan_service.py`, `app/repo_analysis/services/experience_service.py`, `app/repo_analysis/services/mr_experience/git_history_source.py`

## 背景与问题

当前 MR 经验分析自动触发逻辑存在三个问题：

1. **首次必须人工触发**：`_needs_experience_rescan` 在 `not last_sha` 时返回 False（`incremental_scan_service.py:229-231`），新登记仓的首次 MR 分析必须人工跑 `experience --path`。
2. **无回看窗口配置**：自动触发调用 `start_analyze(repo.id, limit=50)` 不传 `since`（`incremental_scan_service.py:214-217`），只取最近 50 条 MR。对于数百人团队的活跃仓，两年 MR 远不止 50 条，覆盖不足。
3. **增量收集不精准**：虽然 `get_latest_analyzed_commit_sha` 隐式追踪了最后收集点（从 `MrExperienceItem` 取 max `committed_at`），但 `start_analyze` 仍用 `since=None, limit=50` 重拉，靠 `existing` 查询去重，重复拉取浪费。

## 目标

- 去掉首次人工限制，新仓登记后自动触发首次分析
- 支持配置 MR 回看周期（默认 730 天 = 2 年）
- 显式追踪最后收集点（SHA + 时间），增量收集只拉新 MR
- 处理分批在后台跨多天推进，不阻塞 incremental scan tick

## 非目标

- 不改 `MrExperienceItem` 模型
- 不改 `PatternSummarizer` / `PatternVectorService` 业务逻辑
- 不改 CLI `experience` 入口的用户可见参数（仍为 `--since` / `--limit`）
- 不做收集/处理完全分离的重构

## 设计

### 架构概览

收集与处理分离：收集（git log + 落 PENDING）廉价且快，一次性做完；处理（LLM 分析）昂贵，分批在后台跨 tick 推进。

**触发流程**（`_maybe_trigger_experience_analyze`）：

```
每个 repo（incremental scan tick）:
  ├─ 已有 RUNNING 任务？ -> 跳过
  ├─ 读 RepoExperienceTask.last_collected_commit_sha
  ├─ 为空（首次）:
  │    └─ start_analyze(since=<today - lookback_days>, limit=max_collect)
  ├─ 非空（增量）:
  │    └─ has_new_entries(after_sha=last_collected_commit_sha)?
  │         ├─ 是 -> start_analyze(after_sha=last_collected_commit_sha, limit=max_collect)
  │         └─ 否 -> 跳过
  └─ 处理：_run_analyze 内部调用 _process_pending_and_failed(max_items=process_batch_size)
```

### 数据模型变更

`RepoExperienceTask`（`app/repo_analysis/models/experience_status.py:22-39`）新增：

```python
last_collected_commit_sha = Column(String(64), nullable=True, comment="最后一次收集到的 MR commit SHA（增量检测用）")
last_collected_committed_at = Column(DateTime, nullable=True, comment="最后一次收集到的 MR 提交时间（观测用）")
```

新增 alembic 迁移。`MrExperienceItem` 不变。

### 配置变更

`app/config/settings.py` 新增：

```python
mr_experience_lookback_days: int = Field(default=730, ge=1, description="MR经验首次分析回看天数", env="MR_EXPERIENCE_LOOKBACK_DAYS")
mr_experience_max_collect_per_run: int = Field(default=5000, ge=1, description="单次收集 MR 上限（保护性）", env="MR_EXPERIENCE_MAX_COLLECT_PER_RUN")
mr_experience_process_batch_size: int = Field(default=50, ge=1, description="单轮处理 PENDING 条目数", env="MR_EXPERIENCE_PROCESS_BATCH_SIZE")
```

### 收集逻辑

`GitHistorySource.collect`（`git_history_source.py:13`）新增 `after_sha: Optional[str]` 参数：

- `after_sha` 非空：`git log after_sha..HEAD --merges`（无 merge 时回退 `--no-merges`）
- `after_sha` 为空：沿用现有 `--since` 逻辑
- 两者都传时以 `after_sha` 优先（增量场景）

新增 `_list_commits_after` 辅助方法，复用 `_run_git` + `_enrich`。

### start_analyze 变更

`ExperienceService.start_analyze`（`experience_service.py:71`）新增 `after_sha: Optional[str]` 参数：

- 传给 `GitHistorySource.collect`
- 收集完成后，取 entries[0]（git log 默认最新优先）更新 `RepoExperienceTask.last_collected_commit_sha` + `last_collected_committed_at`
- 人工触发（无 `after_sha`）也更新高水位，保证人工与自动状态一致

### 触发逻辑变更

`_needs_experience_rescan`（`incremental_scan_service.py:226-232`）改写：

```python
async def _needs_experience_rescan(repo: GitRepository) -> bool:
    async with get_db_session() as db:
        task = await db.scalar(select(RepoExperienceTask).where(RepoExperienceTask.repo_id == repo.id))
        last_sha = task.last_collected_commit_sha if task else None
    if not last_sha:
        return True  # 首次自动触发
    return GitHistorySource.has_new_entries(repo.local_path, after_sha=last_sha)
```

`_maybe_trigger_experience_analyze`（`incremental_scan_service.py:201-224`）：

- 首次：`start_analyze(since=<today - lookback_days>.isoformat(), limit=settings.mr_experience_max_collect_per_run)`
- 增量：`start_analyze(after_sha=last_sha, limit=settings.mr_experience_max_collect_per_run)`

### 处理分批

- `_process_pending_and_failed`（`experience_service.py:193`）新增 `max_items: Optional[int]` 参数，达到上限即返回
- `_run_analyze` 调用时传 `max_items=settings.mr_experience_process_batch_size`
- `_list_repos_with_failed` 改为 `_list_repos_with_pending_or_failed`，覆盖仅有 PENDING 的 repo
- `_retry_loop` 对每个 repo 也传 `max_items`

### 错误处理

- **收集失败**：`last_collected_*` 不更新，下次 tick 重试
- **处理中断**（进程崩溃）：PENDING 条目留 DB，retry loop 跨 tick 继续
- **`after_sha` 在 git 历史中不存在**（rebase 删除）：`git log after_sha..HEAD` 报错，`_run_git` 已捕获 `RuntimeError` 返回空列表；触发逻辑下次走首次重收集（`last_collected_commit_sha` 仍为旧值，`has_new_entries` 返回 False，不会无限重试）。需要补充：检测到 `after_sha` 失效时清空 `last_collected_commit_sha`，触发下次首次重收集。

## 测试

### 单元测试

- `tests/unit/mr_experience/test_git_history_source.py`：`collect(after_sha=...)` 新参数，验证只返回 `after_sha..HEAD` 的条目
- `tests/unit/mr_experience/test_experience_service.py`：
  - `start_analyze(after_sha=...)` 更新高水位
  - 人工触发（无 `after_sha`）也更新高水位
  - `_process_pending_and_failed(max_items=N)` 达上限即停
- `tests/unit/analysis/test_incremental_scan_service.py`：
  - `_needs_experience_rescan` 首次（`last_collected_commit_sha` 为空）返回 True
  - `_needs_experience_rescan` 增量（有 `last_collected_commit_sha`）走 `has_new_entries`
- retry loop 处理纯 PENDING repo

### 功能验证

- `tests/scenarios/mr_experience/test_experience_flow.py`：首次自动触发走全量收集 + 分批处理
- `tests/scenarios/mr_experience/test_incremental_experience_scan.py`：增量只拉新 MR

## 兼容性

- 已有 `RepoExperienceTask` 行的 `last_collected_commit_sha` / `last_collected_committed_at` 为 NULL，下次 incremental scan tick 视为首次，触发全量收集。已分析的 `MrExperienceItem` 不会被重复创建（`existing` 查询去重）。
- 配置默认值保证开箱即用，不需要用户额外设置。
