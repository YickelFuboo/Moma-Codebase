# 增量扫描：删改名清干净 + git 判变

日期：2026-07-17  
状态：已实现（UT：scan_change + cleanup + 原 incremental 回归）

## 目标

1. **别脏**：扫描发现文件缺失（删除/改名旧路径）时，走完整清理（状态 + 向量 + graph），与 excluded 目录一致  
2. **别白跑**：有 `.git` 时用 working tree / HEAD 判变触发重扫，避免仅 mtime touch 误触发；无 git 回退文件数 + mtime

## 非目标

- 文件 content hash 落库  
- 改名检测为「同一 inode 迁移」（git/磁盘侧按删旧+增新处理即可）

## 行为

| 场景 | 行为 |
|------|------|
| 扫到目录内 DB 有、磁盘无 | `FileAnalysisService.delete_file_analysis_data(force=True)` |
| 有 git 且 porcelain 含源码扩展变更 | `_needs_rescan=True` |
| 有 git 且 HEAD ≠ 上次扫描记录的 head | `_needs_rescan=True` |
| 有 git 且干净且 HEAD 未变 | `_needs_rescan=False`（忽略纯 mtime） |
| 无 git / git 探测失败 | 回退 count + max mtime |
| 扫描成功结束 | 若有 git，持久化当前 HEAD（`{RUNTIME_DATA_DIR}/scan_fingerprints/{repo_id}.json`） |

## 产物

- `ScanChangeDetector`
- `AnalysisService._delete_missing_files_in_cur_dir` 对齐完整清理
- UT：`tests/unit/analysis/test_scan_change_and_cleanup.py` + 原 `test_incremental_scan_service.py`
