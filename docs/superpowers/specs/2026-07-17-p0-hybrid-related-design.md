# P0：related 混合检索 + chunks/symbols 独立查询

日期：2026-07-17  
状态：已批准

## 目标

1. 增强 `search related`：向量（符号摘要 + 行块）+ 索引字段精确匹配，融合排序；不阻塞、不 sync。
2. 新增人工调试接口：`search chunks`、`search symbols`（可不作为 Agent 主路径）。
3. 查询结果附带只读 `index` 新鲜度（`last_scan_finished_at` / `index_age_seconds`）。
4. 真仓评测：`tests/scenarios/pando_agent/`，默认仓 `F:/Product_Dev/PANDO/Pando-Agent`（`PANDO_AGENT_PATH` 可覆盖），**全仓 analyze**（`ANALYZE_TARGET=None`），跨模块 ground truth；校验 related 混合命中与 exact 置顶。
5. Precision：符号边界/分层打分；弱词不路径命中；融合按 `file_path` 去重。

## 非目标

- 查询前 analyze/sync
- 新建 `search hybrid` 命令
- 全仓实时 grep

## related 融合

精确命中（`symbol_name` / `file_path` 含子串）加权靠前；再按向量分；去重后 `top_k`。  
item 增加 `match_source`：`exact` | `symbol_summary` | `line_chunk`。
