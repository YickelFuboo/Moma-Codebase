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
3）调用开源软件CodeGraph，对代码仓结构进行解析，并吧CodeGraph的接口封装提供本项目CLI的检索接口。

二、Lib库解析处理
对Lib库中的所有接口进行功能、参数等总结，切片存储，方面后续编码Agent根据需要检索可能相关Lib库。

三、历史 MR 经验沉淀（主要面向 kind=code 的 Repo）
1）支持对指定 Repo 的历史 Merge Request（MR）进行分析：读取 MR 的需求描述或问题描述，结合 MR 中的实际代码变更，识别与需求**强相关**的修改点（文件、位置、变更角色）。
2）将「需求/问题类型 → 应改哪些文件、改什么」自动总结并沉淀为可检索的**开发经验/开发模式**，向量化存储。
3）后续编码 Agent 在启动某类需求开发时，可通过查询接口按需求描述检索相似历史模式，例如：
   - 改告警：需在 `xxx.xls` 中修改告警名称；在 `xxx.go` 中修改告警触发逻辑；在 `....txt` 中修改对外告警说明。
4）经验沉淀仅针对已登记的 Repo（本地目录）；MR 元数据与 diff 来自该 Repo 关联的远程平台或可配置的 MR 数据源（如 GitLab/GitHub 等，具体适配在实现阶段按配置扩展）。

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

本项目依赖开源 **CodeGraph**。在 `mcb` 启动时（进入交互模式，以及执行依赖图谱能力的一次性命令前）须：

1. 检查运行机是否已安装可用的 CodeGraph；
2. 若未安装或不可用，自动安装（或引导完成安装）后再继续；
3. 安装/检测失败时，给出明确错误信息；图谱相关能力不可用时不得静默跳过（除非配置显式关闭图谱，见 env `CODE_GRAPH_ENABLED`）。

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
| `search similar` | 相似代码片段检索 | `--path` + `--code` `[--top-k]` |
| `search related` | 按关键词/描述找相关类、函数、文件 | `--path` + `--keywords` `[--top-k]` |
| `search api` | 按需求检索公开接口摘要（Lib 侧重，code 也可用） | `--path` + `--query` `[--top-k]` |
| `search pattern` | 按需求/问题描述检索历史开发模式与经验 | `--path` + `--query` `[--top-k]` |
| `search dependents` | 查询依赖指定文件的其他文件（CodeGraph，主要 kind=code） | `--path` + `--file` |
| `search dependencies` | 查询指定文件依赖的其他文件（CodeGraph，主要 kind=code） | `--path` + `--file` |

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
  - 代码镜像：`repo add --kind code` → `analyze --path ...` → `search similar|related|...`
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
│   │   ├── codegraph/            # CodeGraph 封装（依赖开源 CodeGraph）
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
