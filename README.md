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

## 命令使用方式

| 命令组 | 一次性命令（`mcb` 开头） | 交互模式（省略 `mcb`） |
|--------|--------------------------|------------------------|
| `repo` | 支持 | 支持 |
| `search` | 支持 | 支持 |
| `migrate` | 支持 | 支持 |
| `analyze` | 不支持 | **仅支持** |

- **一次性命令**：在终端直接执行，适合脚本、CI、快速查询。
- **交互模式**：运行 `poetry run mcb` 进入 `mcb>` 提示符；启动时自动拉起文件分析调度器，适合扫描与分析等后台任务。

```bash
# 进入交互模式
poetry run mcb

# 一次性命令示例
poetry run mcb repo list
poetry run mcb search similar --path F:\myproject --code "def foo"
```

交互模式中输入 `help` 查看子命令，`exit` / `quit` 退出。

## 首次使用

```bash
poetry run mcb migrate
poetry run mcb repo add --path F:\myproject
poetry run mcb
```

## repo（仓库管理）

支持一次性与交互两种写法；交互模式中省略 `poetry run mcb` 前缀。

```bash
# 一次性
poetry run mcb repo add --path F:\myproject [--description "说明"]
poetry run mcb repo list
poetry run mcb repo show --path F:\myproject
poetry run mcb repo delete --path F:\myproject
```

```text
# 交互（mcb> 提示符下）
repo add --path F:\myproject
repo list
repo show --path F:\myproject
repo delete --path F:\myproject
```

## analyze（代码仓分析）

**仅在交互模式中使用**（需先 `poetry run mcb` 进入 `mcb>`）。

`analyze start` 登记扫描任务并立即返回；文件扫描与向量化等由进程内调度器在后台执行。

```text
analyze start --path F:\myproject
analyze status --path F:\myproject
analyze stop --path F:\myproject
analyze clear --path F:\myproject
```

## search（检索与图谱）

支持一次性与交互两种写法。

```bash
# 一次性
poetry run mcb search similar --path F:\myproject --code "def foo()" [--top-k 10]
poetry run mcb search related --path F:\myproject --keywords "auth,login" [--top-k 10]
poetry run mcb search dependents --path F:\myproject --file src/main.py
poetry run mcb search dependencies --path F:\myproject --file src/main.py
```

```text
# 交互（mcb> 提示符下）
search similar --path F:\myproject --code "def foo()"
search related --path F:\myproject --keywords "auth,login"
search dependents --path F:\myproject --file src/main.py
search dependencies --path F:\myproject --file src/main.py
```

## migrate（数据库迁移）

```bash
poetry run mcb migrate
```

交互模式中也可执行：`migrate`

## 推荐工作流

```bash
# 1. 登记仓库（一次性即可）
poetry run mcb repo add --path F:\myproject

# 2. 进入交互，启动分析并查看进度
poetry run mcb
```

```text
mcb> analyze start --path F:\myproject
mcb> analyze status --path F:\myproject
mcb> exit
```

```bash
# 3. 随时一次性检索
poetry run mcb search similar --path F:\myproject --code "class User"
```

## 调试（VS Code / Cursor）

使用 `.vscode/launch.json` 中的 **「mcb: 交互调试（推荐）」** 调试 analyze 相关逻辑；`repo` / `search` 可使用对应的单命令配置。
