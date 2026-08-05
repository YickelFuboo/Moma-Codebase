# MomaCodeBase

本地代码仓分析 CLI 工具（命令名：`mcb`）。把存量代码仓逆向成「数字镜像」，供编码 Agent **参考加速**（非精确全库索引）：检索相似代码、相关文件、调用关系与历史改法。

详细能力、准确率优化与评测对比见 [Design.md](Design.md)。

**使用前必须先完成本机安装。** 装好后任意目录直接调 `mcb`；命令里的 `--path` 指向**业务仓**，不是本工具源码目录。编码 Agent 开发别的项目时，不需要也不应在业务仓里再 `poetry install` 本工具。

## 安装

### 1. 拿到源码并安装依赖

```bash
git clone <本仓库地址>
cd Moma-CodeBase
poetry install
```

### 2. 让系统能找到 `mcb`（二选一）

**推荐：pipx（隔离环境 + 自动进 PATH，便于日后升级）**

```bash
# 需已安装 pipx，并执行过 pipx ensurepath
pipx install .
# 之后升级（在本仓目录或换 git URL）：
# pipx reinstall .
# 或：pipx upgrade MomaCodeBase
```

**或：把 Poetry 虚拟环境里的 Scripts 加入 PATH**

安装后可执行文件一般在：

- Windows：`<本仓>\.venv\Scripts\mcb.exe`
- macOS / Linux：`<本仓>/.venv/bin/mcb`

把该目录加入用户 PATH，新开终端后即可全局使用 `mcb`。

开发本工具时仍可用 `poetry run mcb ...`；**给 Agent / 日常调用请用 PATH 上的 `mcb`。**

### 3. 验证已安装

```bash
mcb --version
mcb doctor
```

`doctor` 返回 JSON 且顶层 `ok: true` 后再继续（含 embedding 探测）。失败时先修配置，不要直接 `setup` / `resolve`。

### 4. 配置

在本仓复制 `env.example` 为 `env`，按需填写模型 key、向量库等（`doctor` / 首次运行也会依赖这些配置）。

- 运行时数据目录：`RUNTIME_DATA_DIR`（默认 `~/.moma-codebase`）
- 模型清单：`{RUNTIME_DATA_DIR}/models/chat_models.json`、`embedding_models.json`
- CodeGraph：`CODE_GRAPH_PROVIDER=codegraph|builtin`（默认 `codegraph`；交互启动时可能自动安装开源 CLI）

配置与索引数据在运行时目录，与「装在哪」分离；升级 mcb 一般不丢已分析索引。

## 命令使用方式

| 命令组 | 一次性命令（任意目录 `mcb ...`） | 交互模式（装好后直接 `mcb`） |
|--------|----------------------------------|------------------------------|
| `setup` | 支持 | 支持 |
| `repo` | 支持 | 支持 |
| `search` | 支持 | 支持 |
| `doctor` | 支持 | 支持 |
| `migrate` | 支持 | 支持 |
| `analyze` | 支持（进程退出后后台任务结束；长任务建议交互） | 支持 |

```bash
# 进入交互模式
mcb

# 一次性命令（可在任意工作目录执行）
mcb repo list
mcb search similar --path F:\myproject --code "def foo"
```

## 首次使用（业务仓）

```bash
mcb migrate
# 一键就绪：doctor + 登记 + analyze，等到可检索
mcb setup --path F:\myproject --kind code
```

改完代码若感觉检索「飘了」，先 `mcb analyze status --path ...` 看 `stale_hint` / `status_message`，必要时再 `analyze`。

## Agent 通过 CLI 对接

前提：**本机已安装 `mcb` 且在 PATH 中**（见上方「安装」）。Agent 在业务项目里可调用 `mcb` CLI，或挂载 MCP（`mcb mcp serve`）；无需把本仓加进业务仓依赖。

查询类输出为 JSON（stdout）。主入口 `search resolve` 与其它 `search *` 使用稳定信封：`ok: true/false`（见 [docs/cli-schemes.md](docs/cli-schemes.md) / `app/cli/schemes.py`）。

正式 Agent Skill：[skills/mcb-resolve/SKILL.md](skills/mcb-resolve/SKILL.md)。

### MCP Server（Cursor 等）

查询类能力也可通过 stdio MCP 挂载（与 CLI 共用同一套服务，返回同样的 JSON 信封）：

```bash
mcb mcp serve
# 或：poetry run python -m MCP
```

Cursor `mcp.json` 示例（把 `mcb` 换成你本机可执行路径，或 Poetry 包装）：

```json
{
  "mcpServers": {
    "mcb": {
      "command": "mcb",
      "args": ["mcp", "serve"]
    }
  }
}
```

工具：`doctor` / `repo_list` / `resolve`（主入口）/ `similar` / `related` / `pattern` / `api` / `dependents` / `dependencies` / `callers` / `callees`。实现见根目录 [`MCP/`](MCP/)。

### 前置条件

1. 本机已安装 `mcb`，`mcb doctor` 通过，`env` 已配置
2. 目标业务仓已 `mcb setup`（或 `repo add` + `analyze`；需要历史经验时再 `experience analyze`）
3. Agent Skill / 工具配置里写 `mcb ...`，不要写死业务仓内的 `poetry run`

### 推荐注册给 Agent 的命令

| 用途 | 命令 |
|------|------|
| 一键就绪 | `mcb setup --path <仓>` |
| 已登记仓 | `mcb repo list` |
| 环境自检 | `mcb doctor` |
| 主检索 | `mcb search resolve --path <仓或上级目录> [--path ...] --query "..."` |
| 相似代码 | `mcb search similar --path <仓或上级目录> [--path ...] --code "..."` |
| 相关定位 | `mcb search related --path <仓或上级目录> [--path ...] --keywords "a,b"` |
| 历史经验 | `mcb search pattern --path <仓或上级目录> [--path ...] --query "..."` |
| Lib API | `mcb search api --path <库或上级目录> [--path ...] --query "..."` |
| 依赖 / 调用链 | `mcb search dependents\|dependencies\|callers\|callees ...` |

`--path` 支持两种用法（可组合，结果并集后融合）：

1. **精确仓**：`--path F:\frontend`（须已 `repo add` / `setup`）
2. **上级目录前缀**：`--path F:\workspace\services`，自动展开其下所有已登记子仓
3. **多 path**：`--path A --path B` 并集

展开时会按命令过滤 `kind`：`similar` / `related` / `pattern` 等只展开 **code**；`search api` 只展开 **lib**；`resolve` 同时覆盖二者。

示例：

```bash
mcb search resolve --path F:\myproject --query "JWT 鉴权怎么做"

# 上级目录：已登记 a/b/c/d、a/b/c/e、a/b/f 时
mcb search resolve --path F:\a\b\c --query "登录鉴权"   # → d + e
mcb search resolve --path F:\a\b --query "登录鉴权"     # → d + e + f

# 多 path 并集
mcb search resolve --path F:\frontend --path F:\backend --query "登录鉴权"
```

Agent 推荐形态：

```bash
mcb search resolve --path F:\myproject --query "JWT 鉴权怎么做" --timeout-ms 60000
```

## repo（仓库管理）

```bash
mcb repo add --path F:\myproject --kind code [--description "说明"]
mcb repo list
mcb repo show --path F:\myproject
mcb repo delete --path F:\myproject
```

`--kind`：`code`（完整项目）或 `lib`（公共逻辑库）。

## analyze（代码仓分析）

`analyze --path` 即启动扫描；文件分析由进程内调度器消费。扫描忽略：内置目录 + 仓根 `.gitignore` + 可选 `.momaignore`。

交互模式 `mcb` 启动后会拉起后台 tick（`ENABLE_INCREMENTAL_SCAN`）：对**已 `repo add` 登记**的仓做变更扫描、未完成补扫与失败重处理。也可主动 `analyze --path` 立刻开扫。

```bash
mcb analyze --path F:\myproject
mcb analyze status --path F:\myproject   # 进度（含 searchable/embedded）/ 新鲜度 / 忽略 / 失败
mcb analyze stop --path F:\myproject
mcb analyze clear --path F:\myproject
```

## search（检索与图谱）

```bash
mcb search resolve --path F:\myproject --query "JWT 鉴权" [--intent auto] [--top-k 10]
mcb search similar --path F:\myproject --code "def foo()" [--top-k 10]
mcb search related --path F:\myproject --keywords "auth,login" [--top-k 10]
mcb search dependents --path F:\myproject --file src/main.py
mcb search dependencies --path F:\myproject --file src/main.py
```

依赖方向与符号调用查询在 `CODE_GRAPH_PROVIDER=codegraph`（默认）下经开源 CLI 适配；亦可切 `builtin` 走自研 Neo4j。

## migrate（数据库迁移）

```bash
mcb migrate
```

## 推荐工作流

```bash
# 1）本机已安装 mcb（见「安装」）
# 2）对业务仓建索引并检索
mcb setup --path F:\myproject --kind code
mcb search resolve --path F:\myproject --query "class User" --timeout-ms 60000
```

或分步：

```bash
mcb repo add --path F:\myproject --kind code
mcb
```

```text
mcb> analyze --path F:\myproject
mcb> analyze status --path F:\myproject
mcb> exit
```

```bash
mcb search resolve --path F:\myproject --query "class User"
```
