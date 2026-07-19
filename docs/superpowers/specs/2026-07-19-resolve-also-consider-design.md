# resolve / related：主列表 + also_consider（分离式 Agent）

日期：2026-07-19  
状态：已实现（UT 43 + Pando resolve/related 19 passed）

## 背景

Cursor 与 Agent 一体，可多轮补搜；mcb 与 Agent 分离，一次 CLI 结果几乎是全部线索。不能只砍短列表抬 Precision，否则漏改面。

## 策略

- `items`：高置信主列表，可带 snippet
- `also_consider`：同次检索多余候选，默认不带 snippet，防漏
- `read_hint`：约定先读 items，改前扫 also_consider

## 截断

| 信号 | items | also_consider |
|------|-------|---------------|
| 强 exact | cap ≤ 3 | 融合池其余 ≤ 8 |
| 弱语义 | cap ≤ 5（现门槛） | 未进主列表的其余 ≤ 8 |

## 非目标

- 不为对齐 Cursor 改索引时延/新鲜度
- also_consider 不默认挂大段源码
