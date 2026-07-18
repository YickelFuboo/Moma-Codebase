# MomaCodeBase

本地代码仓分析 CLI 工具（命令名：`mcb`）。把存量代码仓逆向成「数字镜像」，供编码 Agent 检索相似代码、相关文件、调用关系与历史改法。

详细能力、准确率优化与评测对比见 [Design.md](Design.md)。

## 安装

```bash
poetry install
```

## 配置

复制 `env.example` 为 `env`，按需修改数据库、向量库、Neo4j、模型配置等。

- 运行时数据目录：`RUNTIME_DATA_DIR`（默认 `~/.moma-codebase`）
- 模型清单：`{RUNTIME_DATA_DIR}/models/chat_models.json`、`embedding_models.json`
- CodeGraph：`CODE_GRAPH_PROVIDER=codegraph|builtin`（默认 `codegraph`）

## 命令使用方式

| 命令组 | 一次性命令（`mcb` 开头） | 交互模式（省略 `mcb`） |
|--------|--------------------------|------------------------|
| `repo` | 支持 | 支持 |
| `search` | 支持 | 支持 |
| `doctor` | 支持 | 支持 |
| `migrate` | 支持 | 支持 |
| `analyze` | 支持（进程退出后后台任务结束；长任务建议交互） | 支持 |

```bash
# 进入交互模式（启动时检查/安装 CodeGraph）
poetry run mcb

# 一次性命令示例
poetry run mcb repo list
poetry run mcb search similar --path F:\myproject --code "def foo"
```

## 首次使用

```bash
poetry run mcb migrate
poetry run mcb repo add --path F:\myproject --kind code
poetry run mcb
```

## Agent 通过 CLI 对接

编码 Agent **直接调用一次性 `mcb` 命令**即可，无需另起服务。查询类输出为 JSON（stdout），便于解析。

主入口 `search resolve` 与其它 `search *` 查询均使用稳定信封：`ok: true/false`（见 [docs/cli-schemes.md](docs/cli-schemes.md) / `app/cli/schemes.py`）。

### 前置条件

1. 已 `poetry install`，并配置好 `env`
2. 目标仓已 `repo add` + `analyze`（需要历史经验时再 `experience analyze`）
3. Agent 侧把本仓加入 PATH / 工作目录，或写全路径调用 `poetry run mcb ...`

### 推荐注册给 Agent 的命令

| 用途 | 命令 |
|------|------|
| 已登记仓 | `mcb repo list` |
| 环境自检 | `mcb doctor` |
| 主检索 | `mcb search resolve --path <仓或上级目录> [--path ...] --query "..."` |
| 相似代码 | `mcb search similar --path <仓或上级目录> [--path ...] --code "..."` |
| 相关定位 | `mcb search related --path <仓或上级目录> [--path ...] --keywords "a,b"` |
| 历史经验 | `mcb search pattern --path <仓或上级目录> [--path ...] --query "..."` |
| Lib API | `mcb search api --path <库或上级目录> [--path ...] --query "..."` |
| 依赖 / 调用链 | `mcb search dependents\|dependencies\|callers\|callees ...` |
| 已登记仓 | `mcb repo list` |

`--path` 支持两种用法（可组合，结果并集后融合）：

1. **精确仓**：`--path F:\frontend`（须已 `repo add`）
2. **上级目录前缀**：`--path F:\workspace\services`，自动展开其下所有已登记子仓  
3. **多 path**：`--path A --path B` 并集

展开时会按命令过滤 `kind`：`similar` / `related` / `pattern` 等只展开 **code**；`search api` 只展开 **lib**；`resolve` 同时覆盖二者。

示例：

```bash
poetry run mcb search resolve --path F:\myproject --query "JWT 鉴权怎么做"

# 上级目录：已登记 a/b/c/d、a/b/c/e、a/b/f 时
poetry run mcb search resolve --path F:\a\b\c --query "登录鉴权"   # → d + e
poetry run mcb search resolve --path F:\a\b --query "登录鉴权"     # → d + e + f

# 多 path 并集
poetry run mcb search resolve --path F:\frontend --path F:\backend --query "登录鉴权"
```

在 Cursor / 自研 Agent 里：优先注册主工具 `search resolve`（可直接用仓内 Skill 模板 [skills/mcb-resolve/SKILL.md](skills/mcb-resolve/SKILL.md)）；约定 `--path` 与登记目录一致。JSON 信封见 [docs/cli-schemes.md](docs/cli-schemes.md)。

```bash
# Agent 推荐调用形态
poetry run mcb search resolve --path F:\myproject --query "JWT 鉴权怎么做" --timeout-ms 60000
```

## repo（仓库管理）

```bash
poetry run mcb repo add --path F:\myproject --kind code [--description "说明"]
poetry run mcb repo list
poetry run mcb repo show --path F:\myproject
poetry run mcb repo delete --path F:\myproject
```

`--kind`：`code`（完整项目）或 `lib`（公共逻辑库）。

## analyze（代码仓分析）

`analyze --path` 即启动扫描；文件分析由进程内调度器消费。扫描忽略：内置目录 + 仓根 `.gitignore` + 可选 `.momaignore`。

交互模式 `mcb` 启动后会拉起后台 tick（`ENABLE_INCREMENTAL_SCAN`）：对**已 `repo add` 登记**的仓做变更扫描、未完成补扫与失败重处理。也可主动 `analyze --path` 立刻开扫。

```text
analyze --path F:\myproject
analyze status --path F:\myproject   # 进度 / 新鲜度 / 忽略规则 / 最近失败
analyze stop --path F:\myproject
analyze clear --path F:\myproject
```

## search（检索与图谱）

```bash
poetry run mcb search resolve --path F:\myproject --query "JWT 鉴权" [--intent auto] [--top-k 10]
poetry run mcb search similar --path F:\myproject --code "def foo()" [--top-k 10]
poetry run mcb search related --path F:\myproject --keywords "auth,login" [--top-k 10]
poetry run mcb search dependents --path F:\myproject --file src/main.py
poetry run mcb search dependencies --path F:\myproject --file src/main.py
```

依赖方向与符号调用查询在 `CODE_GRAPH_PROVIDER=codegraph`（默认）下经开源 CLI 适配；亦可切 `builtin` 走自研 Neo4j。

## migrate（数据库迁移）

```bash
poetry run mcb migrate
```

## 推荐工作流

```bash
poetry run mcb repo add --path F:\myproject --kind code
poetry run mcb
```

```text
mcb> analyze --path F:\myproject
mcb> analyze status --path F:\myproject
mcb> exit
```

```bash
poetry run mcb search resolve --path F:\myproject --query "class User"
```
