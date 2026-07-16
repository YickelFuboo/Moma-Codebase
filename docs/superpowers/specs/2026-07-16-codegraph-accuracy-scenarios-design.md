# CodeGraph 查询适配 + 场景准确率测试设计

日期：2026-07-16  
状态：已批准（用户确认方案 A + 准确率框架）

## 背景与目标

当前场景测试仅断言「有命中即 Pass」，无法验证：

1. 图谱关系是否与本仓真实 import/调用一致；
2. 向量 similar/related 的命中准确率。

约束：默认 `CODE_GRAPH_PROVIDER=codegraph`。查询未适配时先完成功能适配，再写准确率用例。

## 方案选型

采用 **CLI 封装（方案 A）**：

- 生成：已有 `codegraph init`
- 查询：封装 `callers` / `callees` / `query`（`--json`）与 `node -f <file> --symbols-only`（解析文件级依赖）
- 不引入 Node SDK 进程内依赖

## 功能适配

### 现有 API（与 builtin 契约对齐）

| API | CLI 映射 | 成功 content |
|-----|----------|--------------|
| `query_dependents_of_file` | `node -f <file> --symbols-only` → Called by / “used by N files” | `{dependents: [rel_paths]}` |
| `query_dependented_of_file` | 同上 → Calls →（过滤同文件与明显非项目边） | `{dependented: [rel_paths]}` |
| `query_file_summary` | `node --symbols-only` Symbols 段 | `{files: {path: {name, language?, classes, functions}}}` |

### 扩展 API（符号级关系）

在 `CodeGraphSearchBase` + Gateway + CLI 增加：

| API | CLI | content |
|-----|-----|---------|
| `query_callers_of_symbol(repo_id, symbol)` | `callers <symbol> -j` | `{callers: [{name, kind, file_path, start_line}]}` |
| `query_callees_of_symbol(repo_id, symbol)` | `callees <symbol> -j` | `{callees: [...]}` |

CLI：`mcb search callers` / `mcb search callees`。

### 实现要点

1. `_CliSearch` 按 `repo_id` 查库解析本地仓路径，执行 CLI 时带 `-p <repo_local_path>`。
2. `find_codegraph_cli`：`PATH` 优先；失败则回退 npm 全局目录下的 `codegraph`/`codegraph.cmd`。
3. 子进程统一 `encoding=utf-8, errors=replace`。
4. 去掉「未适配请改用 builtin」占位返回；对应 UT 改为成功路径或解析契约。
5. `builtin` 对新符号 API：可先返回明确 unsupported，或后续补 Neo4j；本阶段准确率场景只跑 `codegraph`。

## 准确率测试框架

### 目录

```
tests/scenarios/
  framework/
    accuracy.py          # Precision/Recall、阈值判定、套件均值汇总
    case_spec.py         # CaseSpec 数据结构
    ground_truth.py      # 本仓固化期望集合
  graph/                 # 图谱关系用例
  vector_similar/        # 相似检索用例
  vector_related/        # 相关检索用例
  base.py                # 保留并扩展 query helpers
```

### 指标

对每个用例，期望集合 \(E\)、实际命中集合 \(H\)（路径或规范化符号键）：

- Precision = \(|H \cap E| / |H|\)（\(H\) 空则为 0）
- Recall = \(|H \cap E| / |E|\)（\(E\) 空则跳过或记 N/A）
- Pass：Precision ≥ 阈值 **且** Recall ≥ 阈值（默认 0.6，子场景可覆盖）
- 套件结束：打印各用例指标 + 平均 Precision / 平均 Recall

向量场景可额外约束 `top_k`，\(H\) 取返回的前 k 条路径集合。

### 规模（约 24～28）

- **graph**（~10–12）：文件 dependents/dependencies；符号 callers/callees（如 `create_search`、`CodeGraphGateway`）
- **vector_similar**（~8–10）：固定代码片段 → must-hit 路径集合
- **vector_related**（~6–8）：关键词 → must-hit；部分开/关符号摘要

Ground truth 人工从本仓源码固化，不动态猜测。

旧「软路径片段 / unsupported 契约」用例删除或改写为准确率用例。

## 验收

1. 默认 provider=`codegraph` 下，dependents/dependencies/file_summary/callers/callees 可返回 `result=True` 与结构化 content。
2. `pytest tests/scenarios -m scenario` 跑通约 20+ 用例，报告含每用例准确率与均值。
3. README/PRD 中「codegraph 未适配请改用 builtin」表述更新为已适配说明。

## 非目标（本阶段）

- 不把准确率场景绑到 Neo4j/`builtin`
- 不引入 Node SDK 进程内集成
- 不为每个用例单独写 README
