# 找代码更准：难例评测 + 全仓 analyze（方案 A）

日期：2026-07-18  
状态：已批准执行

## 目标

在真实业务仓上抬高 similar / related 难例命中（Top1 / P@短列表），不先做跨仓/文档。

## 评测仓

| 仓 | 路径 | analyze 范围 |
|----|------|----------------|
| Pando-Agent | 既有 `PANDO_AGENT_PATH` / 默认外仓 | `app`（产品全仓） |
| KnowledegBase-Service | `参考/KnowledegBase-Service`（自 `F:\Product_Dev\KnowledegBase-Service` 复制）；可用 env 覆盖 | `app`（产品全仓） |

## 流程

1. 补难例 GT（similar 弱改写、related 短词/自然语言）
2. baseline（现有索引或首次 analyze）
3. 仅对短板改 rerank / 归一化（切片仅在召回阶段无候选时再动）
4. 开符号摘要 **全 `app/` analyze** 后复测
5. 输出 before/after

## 非目标

跨仓检索、文档索引、resolve 体验大改、远程 MR API。
