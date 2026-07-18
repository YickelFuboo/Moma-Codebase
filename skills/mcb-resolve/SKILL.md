---
name: mcb-resolve
description: >-
  Use MomaCodeBase (mcb) local code search via search resolve.
  Trigger when locating definitions, similar code, call relations, or past change patterns
  in a registered local repo. Prefer this over inventing paths.
---

# MomaCodeBase — Agent 主工具

## When to use

- 用户问「某某逻辑在哪 / 谁调用 / 以前怎么改」且目标仓已 `mcb repo add` + `analyze`
- 需要短列表路径 + 可选源码片段喂进上下文

## Primary command

```bash
poetry run mcb search resolve --path <REGISTERED_OR_PARENT_PATH> --query "<USER_QUESTION>" --timeout-ms 60000
```

- 可重复 `--path`；上级目录会展开其下已登记子仓（code+lib）。
- 默认带 `snippet`；体积过大时加 `--no-with-content`。
- stdout **只有 JSON**；解析顶层 `ok`。

## Response contract

成功：`ok === true`，读 `items[]`（`file_path` / `symbol_name` / `snippet` / `why`）、`intent`、`index`。  
失败：`ok === false`，读 `error.code` / `error.message`；退出码 2=业务，3=超时。

完整契约：仓库内 `docs/cli-schemes.md`（实现 `app/cli/schemes.py`）。

装机自检：`poetry run mcb doctor`（JSON；`ok=false` 时退出码 2）。

## Do / Don't

- **Do**：主路径只用 `search resolve`；根据 `items` 再决定是否读全文件。
- **Do**：`index.index_age_seconds` 很大时，另开任务跑 `mcb analyze --path ...`，不要在 resolve 里假设已同步。
- **Don't**：不要默认拆成一串 similar/related/callers 自己拼，除非用户明确只要某一通道。
- **Don't**：未登记 path 时先 `mcb repo list` / `mcb doctor`，不要猜测仓库根。

## Optional tools

| 场景 | 命令 |
|------|------|
| 已登记仓 | `mcb repo list` |
| 环境自检 | `mcb doctor` |
| 只要相似代码 | `mcb search similar --path ... --code "..."` |
| Lib API | `mcb search api --path ... --query "..."` |
