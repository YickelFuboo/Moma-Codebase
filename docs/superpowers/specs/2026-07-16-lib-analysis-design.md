# Lib 库解析处理设计

日期：2026-07-16  
状态：已批准（方案 1 + 用户确认边界后进入实现）

## 目标

对 `kind=lib` 的本地目录：抽取公开接口 → LLM 摘要 → 向量化 → `search api` 检索。

## 已定边界

| 项 | 选择 |
|----|------|
| 模块 | 独立 `app/lib_analysis/`（方案 1） |
| 语言 | Python + Go + Java |
| 公开规则 | 语言惯例（Py `__all__`/非 `_`；Go 导出；Java `public`） |
| CodeGraph | 不做 |
| 查询 | 仅 `search api`；其余对 lib 明确报错 |
| 摘要 | LLM（失败则签名+docstring 回退） |
| 状态表 | 复用 `repo_analysis_tasks` / `repo_file_analysis_state`（按 `repo_id`） |

## 架构

```text
analyze --path (kind=lib)
  → AnalysisService.start_scan（跳过 CodeGraph）
  → FileAnalysisService worker
  → LibFileProcessor：AST → 公开过滤 → LLM → api 向量空间

search api --path --query
  → LibSearchService（仅 kind=lib）
```

## 向量

- 空间名：`lib_{repo_id}_api_summary_{dim}`
- `analysis_type`：`api_summary_vector`
- 字段映射到 LanceDB 通用 schema：`symbol_kind`(api_kind) / `symbol_name`(api_name) / `content`(signature) / `summary` / 行号 / `file_path`
- 对外 `search api` 仍返回 `api_kind` / `api_name` / `signature` 等业务字段

## 非目标

- Lib 的 similar/related/dependents/callers
- MR experience
- 独立状态表迁移

## 完备性自检（实现后）

| 项 | 状态 |
|----|------|
| 独立 `lib_analysis` 模块 | ✅ |
| Py/Go/Java 公开规则抽取 | ✅ |
| LLM 摘要 + 回退 | ✅ |
| 独立 API 向量空间 | ✅ |
| `analyze` kind 分流且跳过 CodeGraph | ✅ |
| Lib 仅扫 `.py/.go/.java` | ✅ |
| `search api` + kind 守卫 | ✅ |
| 未分析时明确报错（非空成功） | ✅ |
| 测试文件跳过 | ✅ |
| UT + 场景测试 | ✅ `tests/unit/lib_analysis`、`tests/scenarios/lib_api` |
