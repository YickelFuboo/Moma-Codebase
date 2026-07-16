# MomaCodeBase

本地代码仓分析 CLI 工具（命令名：`mcb`）。

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

## repo（仓库管理）

```bash
poetry run mcb repo add --path F:\myproject --kind code [--description "说明"]
poetry run mcb repo list
poetry run mcb repo show --path F:\myproject
poetry run mcb repo delete --path F:\myproject
```

`--kind`：`code`（完整项目）或 `lib`（公共逻辑库）。

## analyze（代码仓分析）

`analyze --path` 即启动扫描；文件分析由进程内调度器消费。

```text
analyze --path F:\myproject
analyze status --path F:\myproject
analyze stop --path F:\myproject
analyze clear --path F:\myproject
```

## search（检索与图谱）

```bash
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
poetry run mcb search similar --path F:\myproject --code "class User"
```
