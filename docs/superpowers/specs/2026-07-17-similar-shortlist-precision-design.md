# similar 短列表高精度

日期：2026-07-17  
状态：已实现（Pando similar 6/6：avg P=100% R=100%，列表长度多为 1）

## 目标

Agent 侧 similar 返回「短而准」候选，集合 Precision 目标约 60%（P@3 / 短列表），Recall@短列表保持 100%。

## 策略（仅检索侧，不重索引）

1. similar 独立分数门槛 `SIMILAR_SCORE_RATIO_FLOOR=0.82`（高于 related 的 0.55）
2. 软上限：弱信号最多 `SIMILAR_SOFT_CAP=3`
3. 强信号最多 2；极强（路径 stem / 高 symbol_score）最多 1
4. 同目录配额：每个父目录最多 `SIMILAR_DIR_QUOTA=1` 条

## 非目标

- 不改 embedding / 不强制 re-analyze
- 不改 related 的截断常数
