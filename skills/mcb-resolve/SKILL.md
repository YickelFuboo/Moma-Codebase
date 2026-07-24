---
name: mcb-resolve
description: >-
  Use MomaCodeBase (mcb) local code search via search resolve.
  Trigger when locating definitions, similar code, call relations, or past change patterns
  in a registered local repo. Prefer this over inventing paths.
  Product: reference accelerator for coding Agents — not a perfect index.
---

# MomaCodeBase — Agent 主工具

定位：**参考加速，非精确索引**。命中用于缩小阅读范围；改完代码若感觉飘，先看索引是否过期。

## Cursor / Agent 安装（3～5 步）

1. **本机先安装 `mcb`**（见仓库 [README.md](../../README.md)「安装」：`poetry install` + pipx 或把 `.venv/Scripts` 加入 PATH），配置 `env`
2. 验证：`mcb doctor`（需 `ok: true`）
3. 对目标业务仓：`mcb setup --path <REGISTERED_PATH>`
4. 把本 Skill 注册给 Agent（或复制本文件到 Agent skills）
5. 主调用只用下面的 `search resolve`（写 `mcb`，不要 `poetry run`）

Agent 工作目录可以是任意业务项目；**不要**在业务仓里再装一份本工具。

## When to use

- 用户问「某某逻辑在哪 / 谁调用 / 以前怎么改」且目标仓已 `mcb setup`（或 `repo add` + `analyze`）
- 需要短列表路径 + 可选源码片段喂进上下文

## Primary command

```bash
mcb search resolve --path <REGISTERED_OR_PARENT_PATH> --query "<USER_QUESTION>" --timeout-ms 60000
```

- **默认超时 30–60s**（推荐 `60000`）。超时后看失败信封；可降 `--top-k` 或缩小 `--path` 再查。
- 可重复 `--path`；上级目录会展开其下已登记子仓（code+lib）。
- 默认带 `snippet`；体积过大时加 `--no-with-content`。
- stdout **只有 JSON**；解析顶层 `ok`。

## 索引就绪

- 若 `ok === false` 且 `error.code === "index_not_ready"`：先 `mcb analyze status --path ...` / `mcb setup --path ...`，不要把空命中当成「代码里没有」。
- 成功结果里仍读 `index` / `stale_hint`；`index_age_seconds` 很大时另开 `mcb analyze --path ...`。

## Do / Don't

- **Do**：主路径只用 `search resolve`；先读 `items`（可含 snippet），**改代码前扫一遍 `also_consider` 路径**（防漏；默认无大段源码）。
- **Do**：关系查询用 `dependents` / `callers` / `callees`，不要把定位结果里的图谱当调用链。
- **Do**：单通道失败时仍可用其它通道结果；看 `channel_errors`（部分成功）。
- **Don't**：不要默认拆成一串 similar/related/callers 自己拼，除非用户明确只要某一通道。
- **Don't**：未登记 path 时先 `mcb repo list` / `mcb doctor` / `mcb setup`，不要猜测仓库根。
- **Don't**：忽略 `read_hint`；分离式 Agent 不能像 IDE 一样自动补搜。

## Response contract

成功：`ok === true`，读：

- `items[]`：主推荐（`file_path` / `symbol_name` / `snippet` / `why`）
- `also_consider[]`：防漏候选（路径 + `why`，通常无 snippet）
- `channel_errors`：可选；某通道超时/失败时仍可能有 `items`
- `read_hint` / `intent` / `index`

失败：`ok === false`，读 `error.code` / `error.message` / `error.details`；退出码 2=业务，3=超时。

| code | 含义 |
|------|------|
| `index_not_ready` | 尚无可搜索文件，先 analyze/setup |
| `timeout` | 整次 `--timeout-ms` 超时；可降 top_k / 缩 path |
| `repo_not_found` | path 未登记 |

完整契约：仓库内 `docs/cli-schemes.md`（实现 `app/cli/schemes.py`）。

装机自检：`mcb doctor`（JSON；`ok=false` 时退出码 2）。

## 超时与降级

1. 默认 `--timeout-ms 60000`
2. 若超时或偏慢：`--top-k 5`，或把 `--path` 收到更小的已登记子目录
3. 若 `channel_errors` 非空但 `items` 有内容：按已有命中继续，并告知用户部分通道失败
4. 索引未就绪：转 `setup` / `analyze status`，不要瞎编路径

## Optional tools

| 场景 | 命令 |
|------|------|
| 一键就绪 | `mcb setup --path ...` |
| 已登记仓 | `mcb repo list` |
| 环境自检 | `mcb doctor` |
| 分析进度 | `mcb analyze status --path ...` |
| 只要相似代码 | `mcb search similar --path ... --code "..."` |
| Lib API | `mcb search api --path ... --query "..."` |
