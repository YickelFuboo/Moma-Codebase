# 简介
本项目是个代码仓分析项目，能对存量代码仓进行逆向分析形成代码仓的“数字镜像空间”，支撑后续编码Agent快速检索编码任务相关信息。
本项目采用CLI框架，你需要参考Claude Code的方式，支持：
1. CLI页面
2. MomaB xxxx命令行执行
3. 在CLI页面xxx 执行命令

说明：产品名可称 MomaB / MomaCodeBase；CLI 可执行名以 `mcb` 为准（与现仓一致）。编码 Agent 仅通过 CLI / 一次性命令行调用，不另开 HTTP/SDK。

# 功能
一、代码仓解析处理
1）支持对代码仓进行源码片段切面，并进行向量化。后续编码Agent可以基于描述查找代码片段、简介查找可能已需求相关的文件与函数。后续Agent也可以直接需要编码的代码逻辑，直接查找代码仓中是否已有相似的逻辑作为参考。
2）支持对代码仓中所有类、函数进行使用大模型概要总结，并对概要总向量化存储。后续方面编码Agent根据描述找到可能与需求相关的类、函数以及所在文件。
3）通过 CodeGraph 对代码仓结构进行解析，并封装为本项目统一图谱能力（Gateway + CLI）。CodeGraph 提供统一入口，由 ENV `CODE_GRAPH_PROVIDER` 选择实现：`codegraph`（开源 CLI，默认）或 `builtin`（自研 Neo4j）。交互 CLI 启动时检查开源 CLI 是否已安装，缺失则尝试自动安装。封装能力覆盖：**文件级依赖方向查询**、**符号级调用关系查询**、**文件符号摘要**，以及图谱生成/增量更新（详见「2.1 CodeGraph 封装能力」）。

二、Lib库解析处理
对 Lib 库中的公开接口进行抽取、功能/参数 LLM 摘要并向量化存储，供编码 Agent 通过 `search api` 按需求检索。当前实现：`kind=lib`；语言 Python/Go/Java；公开规则为语言惯例；不做 CodeGraph；查询仅开放 `search api`。

三、历史 MR 经验沉淀（主要面向 kind=code 的 Repo）
1）支持对指定 Repo 的历史合入进行分析：默认从**本地 git**读取（有 merge commit 则用 merge，否则用普通 commit），结合 commit message 与 diff，经规则筛选强相关文件后由 LLM 总结「改哪些文件、改什么」。
2）将「需求/问题类型 → 应改哪些文件、改什么」沉淀为可检索的开发经验，向量化存储；LLM 失败记 `failed` 且不进向量，支持定时重试，成功后才可检索。
3）编码 Agent 可通过 `search pattern` 按需求描述检索相似历史模式。
4）经验沉淀仅针对已登记的 `kind=code` Repo；远程 GitHub/GitLab MR API 为后续扩展（本阶段以本地 git 为准）。

说明：
- Lib 本质也是本地目录型 Repo，只是不是可运行的完整项目，而是提供公共逻辑；因解析框架不同，管线单列。
- 代码仓与 Lib 在本项目中均由用户指定**本地目录**；登记时用 `--kind code|lib` 区分，便于后续功能互操作复用。
- 历史 MR 经验沉淀默认面向 `kind=code`；Lib 一般不作为 MR 经验分析对象。


# 接口

## 1. 入口形态

| 形态 | 写法 | 说明 |
|------|------|------|
| 交互 CLI | 运行 `mcb` 进入 `mcb>` 提示符，再执行子命令 | 适合长时间分析、查看进度 |
| 一次性命令 | `mcb <子命令> ...` | 适合脚本与编码 Agent 调用 |

三类业务命令：
1. **生成类**：指定 Repo/Lib 本地目录 → 解析分析 → 结果落库（含源码镜像分析、可选的历史 MR 经验分析）
2. **查询类**：必须先指定要查询的 Repo/Lib 本地路径 → 按需检索（含开发模式/经验检索）

## 2. 启动依赖：CodeGraph

本项目依赖 CodeGraph，并通过 `CodeGraphGateway` 统一对外。配置：

| ENV | 含义 | 默认 |
|-----|------|------|
| `CODE_GRAPH_ENABLED` | 是否启用图谱能力 | `true` |
| `CODE_GRAPH_PROVIDER` | `codegraph`（开源 CLI）或 `builtin`（自研 Neo4j） | `codegraph` |

行为：

1. 进入 `mcb` 交互模式时检查当前 provider 是否就绪；`codegraph` 下若未安装 `codegraph` CLI 则尝试自动安装（`npm i -g @colbymchenry/codegraph`）；
2. 生成/查询图谱一律经 `CodeGraphGateway`，禁止业务层直接绑定某一实现；
3. `CODE_GRAPH_ENABLED=false` 时跳过就绪检查与图谱任务；
4. 默认使用 `codegraph`；`builtin` 作为自研 Neo4j 备选实现，契约与 Gateway 对齐。

## 2.1 CodeGraph 封装能力

对外只暴露 `CodeGraphGateway`；业务与 CLI 不直接调用某一 provider。能力分 **生成** 与 **查询** 两类。

### 生成（Generator）

| 能力 | 说明 | 主要使用方 |
|------|------|------------|
| `generate_graph` | 对本仓构建/重建图谱索引 | `analyze` 管线 |
| `update_files` | 按变更文件增量更新图谱 | 文件级重分析 |
| `delete_file_graph` / `delete_repo_graph` | 删除文件或整仓图谱数据 | `analyze clear` / `repo delete` |

`codegraph` 实现映射开源 CLI（如 `codegraph init` / 增量 sync）；`builtin` 写 Neo4j。

### 查询（Search）——文件级

| Gateway / Search API | CLI | 语义 | 成功返回（content 示意） |
|----------------------|-----|------|--------------------------|
| `query_dependents_of_file(repo_id, file)` | `search dependents --path ... --file ...` | 谁依赖本文件（反向依赖） | `{ "dependents": ["rel/path/a.py", ...] }` |
| `query_dependented_of_file(repo_id, file)` | `search dependencies --path ... --file ...` | 本文件依赖谁（出边依赖） | `{ "dependented": ["rel/path/b.py", ...] }` |
| `query_file_summary(repo_id, file_paths)` | （内部/编排用；可按需补 CLI） | 文件内类/方法/函数清单 | `{ "files": { "<path>": { "classes": [...], "functions": [...] } } }` |

说明：路径均为仓内相对路径；查询前目标 Repo 须已登记，且图谱已生成（`analyze` 或等价 init）。

### 查询（Search）——符号级

| Gateway / Search API | CLI | 语义 | 成功返回（content 示意） |
|----------------------|-----|------|--------------------------|
| `query_callers_of_symbol(repo_id, symbol)` | `search callers --path ... --symbol ...` | 哪些函数/方法调用了该符号 | `{ "callers": [{ "name", "kind", "file_path", "start_line" }] }` |
| `query_callees_of_symbol(repo_id, symbol)` | `search callees --path ... --symbol ...` | 该符号调用了哪些函数/方法 | `{ "callees": [{ "name", "kind", "file_path", "start_line" }] }` |

说明：`symbol` 为符号名（如 `create_search`、`CodeGraphGateway`）；`codegraph` 默认实现映射开源 CLI 的 `callers` / `callees`；与文件级 DEPENDS_ON 互补，用于 Agent「从某函数出发追调用链」。

### Provider 职责

| Provider | 默认 | 生成 | 文件级查询 | 符号级查询 |
|----------|------|------|------------|------------|
| `codegraph` | 是 | 开源 CLI 索引（`.codegraph/`） | 适配 CLI（如 `node --symbols-only` 等） | `callers` / `callees --json` |
| `builtin` | 否 | AST + Neo4j | Neo4j `DEPENDS_ON` / 文件摘要 | 与 Gateway 契约对齐；未实现时返回明确错误 |

约定：

1. 查询失败返回 `QueryResponse(result=False, message=...)`，不抛未处理异常冒充空成功。
2. CLI 查询类输出统一 JSON（stdout），便于编码 Agent 解析。
3. 场景/回归测试应对上述能力做 **准确率** 校验（Precision/Recall 相对本仓 ground truth），而非仅「有结果即 Pass」。

## 3. 生成类命令

| 命令 | 作用 |
|------|------|
| `repo add --path <本地目录> --kind code\|lib [--description ...]` | 登记代码仓或 Lib（`kind` 必选） |
| `repo list` | 列出已登记项（含 kind） |
| `repo show --path <本地目录>` | 查看详情 |
| `repo delete --path <本地目录>` | 删除登记及分析数据（不删除磁盘源码目录） |
| `analyze --path <本地目录>` | **启动**解析分析：按登记的 kind 走对应管线并落库 |
| `analyze status --path <本地目录>` | 查看扫描/分析进度 |
| `analyze stop --path <本地目录>` | 停止进行中的扫描 |
| `analyze clear --path <本地目录>` | 清空该目标的分析数据 |
| `experience analyze --path <本地目录> [--since <日期>] [--limit <N>]` | 拉取并分析该 Repo 历史 MR，沉淀开发经验（仅 kind=code） |
| `experience status --path <本地目录>` | 查看 MR 经验分析进度 |
| `experience clear --path <本地目录>` | 清空该 Repo 已沉淀的经验数据 |

约定：
- `--path` 为用户指定的本地目录，且须已通过 `repo add` 登记。
- `kind` 以登记时为准；`analyze` / `experience` 不再传 kind，避免与登记不一致。
- `analyze` 本身即启动，无 `start` 子命令。
- `experience analyze` 与源码 `analyze` 独立：可先做代码镜像分析，再按需做 MR 经验沉淀；也可分次执行。
- `experience` 在 `kind=lib` 上执行时应明确报错。

## 4. 查询类命令

统一用 `--path` 定位已登记的 Repo/Lib；内部解析实体与 kind，再调用对应检索实现。命令面尽量统一，便于后续跨 kind 互操作。

| 命令 | 能力 | 主要参数 |
|------|------|----------|
| `search similar` | 相似代码片段检索（向量） | `--path` + `--code` `[--top-k]` |
| `search related` | 按关键词/描述找相关类、函数、文件（向量） | `--path` + `--keywords` `[--top-k]` |
| `search api` | 按需求检索公开接口摘要（Lib 侧重，code 也可用） | `--path` + `--query` `[--top-k]` |
| `search pattern` | 按需求/问题描述检索历史开发模式与经验 | `--path` + `--query` `[--top-k]` |
| `search dependents` | 查询依赖指定文件的其他文件（CodeGraph 文件级） | `--path` + `--file` |
| `search dependencies` | 查询指定文件依赖的其他文件（CodeGraph 文件级） | `--path` + `--file` |
| `search callers` | 查询调用指定符号的函数/方法（CodeGraph 符号级） | `--path` + `--symbol` `[--limit]` |
| `search callees` | 查询指定符号调用的函数/方法（CodeGraph 符号级） | `--path` + `--symbol` `[--limit]` |

`search pattern` 返回示例形态（示意）：

```json
{
  "path": "/repos/xxx",
  "query": "改告警",
  "items": [
    {
      "title": "告警名称与触发逻辑变更",
      "similarity": 0.91,
      "steps": [
        {"file": "xxx.xls", "action": "修改告警名称"},
        {"file": "xxx.go", "action": "修改告警触发逻辑"},
        {"file": "....txt", "action": "修改对外告警说明"}
      ],
      "source_mrs": ["!123", "!456"]
    }
  ]
}
```

约定：
- 输出统一为 JSON（stdout），便于 Agent 解析。
- 目标未完成（或未开始）分析时，返回明确错误，不返回空结果冒充成功。
- `search pattern` 依赖该 Repo 已执行过 `experience analyze`；无经验数据时明确报错。

## 5. 其他命令

| 命令 | 作用 |
|------|------|
| `migrate` | 数据库迁移 |

## 6. Agent 调用约定

- 仅通过交互 CLI 或一次性 `mcb ...` 命令调用。
- 典型流水线：
  - 代码镜像：`repo add --kind code` → `analyze --path ...` → `search similar|related|dependents|dependencies|callers|callees|...`
  - 开发模式：`experience analyze --path ...` → `search pattern --path ... --query "..."`


# 项目结构

在现有分层上增量扩展：**统一登记 + 按 kind 分流管线**。`infrastructure/` 保持现有结构不变（多项目共享、布局一致，本 PRD 不调整其内部组织）。

```text
app/
├── cli/                          # 唯一对外入口（交互 + 一次性）
│   ├── main.py                   # mcb 根命令；启动时检查/安装 CodeGraph
│   ├── shell.py                  # 交互提示符
│   ├── repo.py                   # 登记管理（含 --kind）
│   ├── analyze.py                # analyze（启动）/ status / stop / clear
│   ├── experience.py             # 历史 MR 经验：analyze / status / clear
│   ├── search.py                 # 查询类命令（含 search pattern）
│   ├── db.py                     # migrate
│   └── common.py                 # path 解析、JSON 输出等
│
├── repo_mgmt/                    # 统一「本地目录实体」管理（kind=code|lib）
│   ├── models/                   # 含 kind 字段
│   ├── schemes/
│   └── services/                 # 登记、path→实体
│
├── repo_analysis/                # kind=code：完整项目解析与检索
│   ├── services/
│   │   ├── codechunk/            # 源码切面
│   │   ├── codesummary/          # 类/函数概要
│   │   ├── codevector/           # 向量化与向量检索
│   │   ├── codegraph/            # CodeGraph 统一入口
│   │   │   ├── gateway.py / base.py / model.py
│   │   │   └── providers/        # 每个 Provider 独立子目录，均继承 base.CodeGraphProvider
│   │   │       ├── builtin/      # 自研 AST + Neo4j
│   │   │       └── codegraph/    # 开源 CLI（默认）
│   │   ├── codeast/              # AST
│   │   ├── mr_experience/        # 历史 MR：拉取、需求-变更对齐、经验总结与向量化
│   │   ├── analysis_service.py   # 源码分析编排
│   │   ├── experience_service.py # MR 经验分析编排
│   │   └── search_service.py     # 检索编排（含 pattern）
│   ├── models/
│   ├── schemes/
│   └── constants/
│
├── lib_analysis/                 # kind=lib：公共库接口解析与检索
│   ├── services/
│   │   ├── api_extract/          # 公开接口抽取
│   │   ├── api_summary/          # 功能/参数摘要（与 codesummary 概念相近，文档模型不同）
│   │   ├── api_vector/           # 切片向量化与检索（与 codevector 共用 infrastructure，schema 不同）
│   │   ├── analysis_service.py
│   │   └── search_service.py
│   ├── models/
│   └── schemes/
│
├── infrastructure/               # 保持现有结构（DB / 向量库 / LLM 等，多项目共享）
├── config/
├── utils/
└── runtime.py
```

## 职责约定

| 层 | 职责 |
|----|------|
| `cli/` | 参数解析、输出、启动时 CodeGraph 检测/安装；不写业务细节 |
| `repo_mgmt/` | 统一登记本地目录，持有 `kind`；`path → 实体` |
| `repo_analysis/` | 完整项目：切面、符号摘要、图谱、检索；历史 MR 经验沉淀 |
| `lib_analysis/` | 公共库：接口抽取、摘要、向量检索（解析框架与 code 不同） |
| `infrastructure/` | 可复用存储与模型能力；布局与现有多项目共享约定保持一致 |

## 按 kind 分流

```text
repo add --path ... --kind code|lib
        ↓
analyze --path ...
        ↓
   读登记 kind
   ├─ code → repo_analysis 管线 → 落库
   └─ lib  → lib_analysis 管线  → 落库

experience analyze --path ...     # 仅 kind=code
        ↓
   mr_experience 管线（MR 描述 + diff → 强相关改点 → 经验落库）

search * --path ...
        ↓
   读登记 kind → 调用对应 search_service（命令面统一；pattern 走经验索引）
```

## 模块重叠说明（summary / vector）

`lib_analysis` 的 `api_summary` / `api_vector` 与 `repo_analysis` 的 `codesummary` / `codevector` 在「摘要/切片 → 向量化 → 检索」上概念相近，但抽取对象与文档模型不同（源码符号/切面 vs 公开 API 签名与参数）。向量写入与模型调用复用 `infrastructure`；领域模块保持分列，不强行合并。
