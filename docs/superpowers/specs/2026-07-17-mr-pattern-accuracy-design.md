# MR pattern 评测闭环

日期：2026-07-17  
状态：已实现（框架 TitleSet + Pando GT/场景）

## 目标

1. pattern 检索结果按 **标题/场景** 评测（非子路径集合）
2. 固定仓（Pando-Agent）强特征 query → 期望标题子串 ground truth
3. 场景断言 Top1 命中 + 标题集合 Precision/Recall，形成回归闭环

## 非目标

- 本轮不重跑 `experience analyze`（依赖已有 pattern 向量空间）
- 不纳入弱短词 query（如 `jwt`/`鉴权`，当前召回不稳）
- 不改 pattern 向量召回算法本身（质量提升属队列后续项）

## 口径

| 项 | 说明 |
|----|------|
| 命中字段 | `items[].title` |
| 匹配 | 期望子串 ⊆ 命中标题（casefold + 空白归一），或反向短标题 |
| Top1 | `require_top1=True` 时主期望须匹配第一条 |
| top_k | 默认 3；单期望时 `min_precision≈0.33` 允许同列表噪音 |

## 产物

- `TitleSetCase` / `AccuracyMetrics.evaluate_titles`
- `PANDO_PATTERN_CASES` + `tests/scenarios/pando_agent/test_pattern_accuracy.py`
- `tests/unit/scenarios/test_title_accuracy.py`
