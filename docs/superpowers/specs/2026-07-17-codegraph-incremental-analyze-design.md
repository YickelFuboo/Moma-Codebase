# CodeGraph analyze 增量编排

日期：2026-07-17  
状态：已落地

## 目标

`analyze` 不新增对外接口；内部按是否已有索引选择全量/增量。

## 规则

| 条件 | 行为 |
|------|------|
| 无 `.codegraph` 且无成功扫描历史 | `generate_graph`（开源=`init`） |
| 存在 `.codegraph`，或曾有 `last_scan_finished_at` | `update_files`（开源=`sync`；builtin 传 PENDING 文件绝对路径） |

## 说明

- 向量侧仍按 mtime 标 PENDING，逻辑不变。
- `codegraph sync` 自行发现变更，可不传文件列表。
- `builtin` 等扫描结束后再取 PENDING 列表做增量。
