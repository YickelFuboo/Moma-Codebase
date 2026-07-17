# 历史 MR 经验沉淀设计（本地 git）

日期：2026-07-16  
状态：已批准（方案 1；用户确认后进入实现）

## 已定边界

| 项 | 选择 |
|----|------|
| 数据源 | 本地 git 仓 |
| 合入策略 | 有 merge 用 merge，否则普通 commit |
| 强相关 | 规则筛文件 + LLM 写步骤 |
| LLM 失败 | 不回退规则文案；任务 `failed`；不进向量；定时/触发重试 |
| 模块 | `repo_analysis` 内独立 `mr_experience` + `experience_service` |
| 范围 | 仅 `kind=code` |

## 架构

```text
experience analyze --path
  → GitHistorySource 采集
  → ChangeFilter 规则 Top-K
  → PatternSummarizer LLM（失败 → failed）
  → PatternVector 仅 ready 写入

search pattern --path --query
  → 仅检索 ready 经验向量
```

## 状态机

`pending → running → ready | failed`；`failed` 可重试。

## 向量

- 空间：`repo_{id}_mr_pattern_{dim}`
- 复用 LanceDB 通用字段：`summary`（经验全文）、`content`（title）、`symbol_name`（commit sha）等

## 完备性自检

| 项 | 状态 |
|----|------|
| 本地 git 采集（merge 优先否则普通 commit） | ✅ |
| 规则筛选 + Top-K | ✅ |
| LLM 总结；失败不回退文案 | ✅ |
| failed 不进向量；定时重试；analyze 重入队重置 retry | ✅ |
| `experience analyze/status/clear` + `search pattern` | ✅ |
| 仅 kind=code | ✅ |
| repo delete 清理经验 | ✅ |
| UT + 场景测试 | ✅ |
