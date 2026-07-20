# MomaCodeBase Design

日期：2026-07-18（章节整理：2026-07-20）  
状态：能力已落地；本文为总设计（已并入原 `docs/superpowers/specs/` 中相关方案）

**怎么读**

| 章节 | 内容 |
|------|------|
| §1–2 | 产品定位与总体架构 |
| §3–4 | **现状设计**：分析 / 检索怎么做（含 NL→Code） |
| §5 | **准度与性能**：各优化点的思路、实现与评测证据（含配置消融） |
| §6–7 | 评测复现与 Agent 对接建议 |
| §8 | 历史专项文档索引 |

CLI 与 Agent 对接见 [README.md](README.md)。

---

## 1. 产品定位

对本地代码仓做逆向分析，形成可检索的「数字镜像」，让编码 Agent 快速拿到：

- 相似实现（给一段代码找参考）
- 相关文件 / 符号（按需求或关键词定位）
- 依赖与调用链（改动影响面）
- 历史改法经验（同类需求以前怎么改）
- Lib 公开 API（公共库接口怎么用）

**对外入口**：仅 `mcb` CLI（交互 + 一次性命令）。Agent 主检索路径为 `search resolve`。不另开 HTTP / MCP / SDK。

---

## 2. 总体架构

```text
repo add --kind code|lib
        │
        ├─ analyze ──► 文件扫描入队 ──► FileAnalysisService workers
        │                 │
        │                 ├─ kind=code：行块向量 + 符号摘要向量 + CodeGraph
        │                 └─ kind=lib ：公开 API 抽取 + 摘要向量（无 CodeGraph）
        │
        ├─ experience analyze ──► 本地 git MR/commit ──► 经验向量
        │
        └─ search * / search resolve ──► 读索引检索（JSON stdout）
```

| 能力开关（ENV） | 作用 |
|-----------------|------|
| `CODE_ANALYSIS_LINE_CHUNK_ENABLED` | 行块 / similar 索引与检索 |
| `CODE_ANALYSIS_SYMBOL_SUMMARY_ENABLED` | 符号摘要 / related 主力通道 |
| `CODE_GRAPH_ENABLED` / `CODE_GRAPH_PROVIDER` | 图谱；`codegraph`（默认）或 `builtin` |
| `MR_EXPERIENCE_ENABLED` | 历史经验沉淀与 `search pattern` |
| `CODE_ANALYSIS_NL_TO_CODE_ENABLED` | NL→Code（多视角 / lexicon；默认 ON） |
| `CODE_ANALYSIS_NL_REWRITE_*` | 可选 LLM 改写（默认 OFF；详见 §5.13） |
| `ENABLE_INCREMENTAL_SCAN` | 文件变更重分析；新 MR 触发经验更新 |
| 忽略规则 | 扫描遵循内置排除 + 仓根 `.gitignore` + 可选 `.momaignore` |
| `analyze status` | 文件计数、`index_age_seconds` / `stale_hint`、增量开关、忽略来源、最近失败 |

向量默认落 LanceDB（`RUNTIME_DATA_DIR` 下）；查询类统一 JSON，未分析时报明确错误，不返回空成功。

---

## 3. 分析场景与技术方案

### 3.1 代码仓镜像（`kind=code`）

`analyze --path` 启动扫描 → 文件状态入队 → 全局调度器拉起每仓 worker 池 → 单文件两阶段调度（快路径）。

单文件在开关允许时按调度解耦执行：

1. **embedding 阶段**（`_analyze_embed_phase`）：AST → 行块向量入库 → 状态 `embedded`（已可 `similar`）或直接 `completed`（未开符号摘要）
2. **符号补齐阶段**（另抢 `embedded` 任务，`_analyze_symbol_phase`）：AST → LLM 符号摘要向量 → `completed`
3. 仓级 **CodeGraph** 生成/增量（见 §3.1.3；与文件队列并行，不阻塞行块可搜）

说明：embedding 与符号摘要**共用 AST 能力但不同任务抢占**，避免 LLM 摘要占满 worker、拖慢「首次可搜」。`analyze status` 中 `searchable_files` = completed + embedded。

#### 3.1.1 行块切片：行窗 + AST 符号体合并入库

实现：`CodeChunkService`（`app/repo_analysis/services/codechunk/code_chunk.py`）  
调用：`FileAnalysisService._analyze_embed_phase` → `merge_chunks` → `CodeVectorService.vectorize_and_store_line_chunks`

**为什么两套切片？**

| 类型 | 解决的问题 | 典型长度 |
|------|------------|----------|
| 行窗滑动 | 覆盖「非符号区」、跨小段逻辑；similar 总能召回局部片段 | 默认目标约 5 行 |
| AST 符号体 | similar 命中**整段函数/类**，避免只命中窗内半截 | 函数可达数百行；小类整段入库 |

**A. 行窗切片（`slice_file`）**

默认参数（可用 ENV 覆盖）：

| 参数 | 默认 | ENV |
|------|------|-----|
| 目标窗口行数 | 5 | `CODE_ANALYSIS_LINE_CHUNK_TARGET_LINES` |
| 重叠行数 | 1 | `CODE_ANALYSIS_LINE_CHUNK_OVERLAP_LINES` |
| 扩展后上限 | 200 | `CODE_ANALYSIS_LINE_CHUNK_MAX_LINES` |

流程：

1. 按 `target_lines` 取初步 `[start, raw_end)`。
2. **`_extend_chunk_end`**：向后扩行，直到满足：
   - 行续接（`\`）结束；
   - 括号 `()[]{}` 在简单扫描下平衡；
   - Python：若末行以 `:` 结尾，继续包含缩进更深的块体。
3. **`_should_drop_chunk`** 过滤低价值块，避免污染向量库：
   - 空白；短块且几乎全是 `import`/`package`/`#include` 等头部；
   - Python：过短 getter/setter、`@property`、仅超短 `return`；
   - Java/Go/C/C++/JS/TS/Rust：模式化 getter/setter、纯 `{`/`}` 噪音等。
4. 步进：`end - overlap`（保证前进），生成带 `start_line`/`end_line`/`text` 的 `LineTextChunk`。

**B. AST 符号体切片（`slice_symbol_bodies`）**

输入：同一次 AST 的 `FileInfo`。

| 符号 | 入库条件 | 默认上限 ENV |
|------|----------|--------------|
| 函数 / 方法 | 行数 ≤ 上限，且正文 strip 后 ≥ 24 字符，且未 drop | `CODE_ANALYSIS_SYMBOL_BODY_MAX_LINES_FUNCTION`（默认 500） |
| 类 | **仅当**行数 ≤ 类上限才整类入库；大类**不切整类**，但仍尝试其方法 | `CODE_ANALYSIS_SYMBOL_BODY_MAX_LINES_CLASS`（默认 120） |

超限符号**跳过**（不切碎），交给行窗覆盖，避免「大类再切一遍」与行窗大量重复。

**C. 合并入库（`merge_chunks`）——核心规则**

```text
merged = symbol_chunks（优先）
for line_chunk in line_chunks:
    if line_chunk 与任一 symbol_chunk 行号区间重叠:
        丢弃该行窗   # 避免同一函数被「整段 + 多个 5 行窗」重复 embedding
    else:
        保留行窗     # 覆盖无符号覆盖的区域
按 (start_line, end_line) 排序 → 向量化写入 line_chunk 空间
```

效果：similar 既能命中完整函数（符号体），又能命中脚本顶层/非符号碎片（行窗）；索引体积可控。

**D. 向量写入防护**

- 空文本跳过 embedding（避免 SiliconFlow `20015` 等非法参数）。
- `CODE_ANALYSIS_EMBED_MAX_CHARS`：超长文本截断或跳过，防止单条打爆模型上限。
- 展示/调试字段与 embedding 文本可分离（见符号摘要）。

#### 3.1.2 符号摘要向量

1. 对 `FileInfo` 中每个符号调 LLM 生成业务向摘要（prompt 强调**业务词 + 使用场景**，少写语法废话）。
2. **LLM 失败/空结果** → `CodeSummary.fallback_summary`（签名 + docstring/注释 + 预览），保证仍可嵌入。
3. **入库 embedding 文本**拼接：`路径 + 符号名 + 摘要`（提升 related 对路径/标识符的可召回性）。
4. **对外展示**的 `summary` 仍用摘要原文，避免把路径噪音显示给用户。
4. 写入独立 `symbol_summary` 向量空间；`search related` / `search symbols` 使用。

说明：摘要质量依赖 **re-analyze 后的新写入**；旧向量不会自动变。

#### 3.1.3 CodeGraph（仓级）

| 条件 | 行为 |
|------|------|
| 无 `.codegraph` 且无成功扫描历史 | `generate_graph`（开源 CLI ≈ `init`） |
| 已有索引或曾有 `last_scan_finished_at` | `update_files`（开源 ≈ `sync`；builtin 传 PENDING 文件） |

- Provider：`CODE_GRAPH_PROVIDER=codegraph|builtin`，统一经 `CodeGraphGateway`。
- **适配层**做结果清洗：`GraphResultNormalizer` 过滤噪音路径；空结果/不支持扩展名给出降级提示；callers/callees 清洗。
- **不改**开源 CodeGraph 内核。

查询能力：文件级 dependents/dependencies、符号级 callers/callees、文件符号清单。

### 3.2 Lib 公开接口（`kind=lib`）

独立模块 `app/lib_analysis/`：

```text
analyze(kind=lib)
  → 扫描仅 .py/.go/.java（跳过测试文件）
  → 公开规则过滤（Py: __all__/非_；Go: 导出；Java: public）
  → LLM 摘要（失败则签名+docstring 回退）
  → 向量空间 lib_{repo_id}_api_summary_{dim}
  → 不做 CodeGraph / MR 经验
```

查询**仅** `search api`；其它 search 对 lib 明确报错。

### 3.3 历史 MR 经验（`kind=code`）

```text
experience analyze
  → GitHistorySource（merge 优先，否则普通 commit）
  → ChangeFilter 规则预筛（lock/纯 sync/无有效文件 → SKIPPED）
  → PatternSummarizer LLM：
        extractable? → 可拆多条经验（场景/模式/anchors/relevant_files）
  → 质量分 / changelog 特征压分 → 仅 ready 写入向量
```

| 状态 | 是否进向量 |
|------|------------|
| ready | 是 |
| skipped / failed | 否（failed 可重试） |

检索：`search pattern`；embed 文本含文件词；**检索侧词面 rerank** 对弱短词即时生效（无需立刻 re-analyze）。

### 3.4 增量与新鲜度

- 向量侧：mtime / 指纹变化 → 文件标 PENDING → worker 重分析。
- 图谱：见 §3.1.3 全量/增量选择。
- `ENABLE_INCREMENTAL_SCAN`：启动交互 `mcb` 后后台 tick；对**已登记**仓做变更扫描、未完成补扫与失败/卡住重处理（人工负责 `repo add`，可选手动 `analyze` 加速首次）。
- 查询结果附带只读 `index`：`last_scan_finished_at` / `index_age_seconds`，供 Agent 判断是否过期。

### 3.5 验收（inspect）

只读导出已落库数据：`inspect chunks|graph|apis`（可选 `--target`/`--file`、`--limit`、`--export`），不触发分析。

---

## 4. 检索场景与技术方案

### 4.1 场景一览

| 场景 | CLI | 典型输入 | 主数据 |
|------|-----|----------|--------|
| 统一编排 | `search resolve` | 自然语言 / 代码 | 多通道融合 |
| 相似代码 | `search similar` | 代码片段 | 行块向量 |
| 相关定位 | `search related` | 关键词 / 符号名 | exact + 符号摘要 +（可选）图谱 |
| 调试 | `search chunks` / `symbols` | 文本 | 单通道向量 |
| 经验 | `search pattern` | 需求描述 | MR 经验向量 |
| Lib | `search api` | 接口需求 | API 摘要向量 |
| 图谱 | `dependents` / `dependencies` / `callers` / `callees` | 路径或符号名 | CodeGraph |

当前 related **默认通道**：仅 `symbol`（exact + 符号摘要）。**不把 CodeGraph 融入定位**（`CODE_ANALYSIS_RELATED_INCLUDE_GRAPH` 默认 false）；关系查询走 `dependents` / `callers` 等。弱结果仍可由 resolve 的 `ResolveWeakFallback` 附带一条 graph。

---

### 4.2 similar：多视角召回 + hybrid rerank + 短列表截断

实现：`SimilarQueryNormalizer` → 多路向量召回 → `SimilarRerankService` → `SearchService.fuse_similar_items` / `_apply_similar_trim`

#### Step 1 — Query 多视角 embedding

对同一段 `code` 构造最多 3 路查询文本（去重后）：

1. **原文**
2. **归一化**：去块注释 / `#`/`//` 行注释，压空白
3. **签名行**：`def`/`class`/`func`/可见性修饰的声明行等

每路分别搜行块向量，再按 `(file_path, start_line, end_line)` 合并取最高向量分。

召回宽度：`fetch_k = max(top_k × 4, 40)`，保证 rerank 有足够候选。

#### Step 2 — Rerank 融合分

权重（当前实现）：

| 分量 | 权重 | 含义 |
|------|------|------|
| 向量分 | 0.42 | embedding 相似度 |
| 词元重叠 | 0.26 | query token ∩ content token |
| 符号名命中 | 0.10 | query 中抽出的 def/class 名是否出现在 content |
| 稀有 token | 0.12 | 长度≥6 或含 `_` 的标识符命中（弱改写关键） |
| 路径段 | 0.10 | 稀有词与 `file_path` 段/stem 对齐（避免 session↔sessions 误伤） |

按融合分排序后 **按 `file_path` 去重**（每文件保留最高分一条）。

#### Step 3 — 短列表截断（高精度）

相对 related 更严：

| 规则 | 取值 |
|------|------|
| 相对 top1 分数门槛 | `score ≥ top1 × 0.82` |
| 同父目录配额 | 每目录最多 1 条 |
| 信号软上限 | 弱≤3；强≤2；极强（路径 stem 命中或 symbol_score≥0.8）≤1 |

Agent 得到「短而准」列表；近原文场景常收敛到 **n=1**。

---

### 4.3 related：exact + 符号向量 + 图谱融合

#### Exact（`ExactMatchService`）

- **只扫已入库向量元数据**，不扫磁盘、不触发 analyze。
- **符号通道**：仅按 `symbol_name` 分层打分（全名 3.0 → 后缀 → CamelCase 边界 → 长子串）；**不再用路径给符号 exact 加分**（避免引用文件靠路径蹭「定义」）。
- 短词 / 弱词（`app`/`agent`/`core` 等）禁止靠拆词蹭命中。
- **路径通道**单独：`score_path_keyword`（完整路径片段、段相等、stem 全等）；弱词同样禁用。

#### 向量通道

- 符号摘要向量（主力）
- 行块向量（可选；找定义场景噪声大）

#### CodeGraph 通道

对 keywords 查 callers/callees，命中文件以固定分写入；`match_source=codegraph`。  
**用途**：补语义定位（如 memory 相关文件），**不是**「符号定义文件」的主答案来源。

#### 融合与截断（`fuse_related_items`）

1. exact 置顶（高 `exact_tier`）
2. 再按向量/图谱分
3. 按 `file_path` 去重
4. 相对 top1：`score ≥ top1 × 0.55` 截断
5. 有强符号 exact 时不硬凑满 `top_k`

item 带 `match_source`：`exact` | `symbol_summary` | `line_chunk` | `codegraph`。

---

### 4.4 resolve：规则路由 + 多通道融合 + 弱结果兜底

实现：`SearchIntentRouter` → 并行 `_run_channel` → `_fuse_items` → `ResolveWeakFallback` → `ResolveResultPresenter`

#### Intent

| 值 | 别名 | 通道 |
|----|------|------|
| auto | （默认） | 规则检测 |
| similar | | similar |
| related | locate | related + similar + grep（开关裁剪） |
| pattern | experience | pattern + related |
| api | | api（仅 lib） |
| graph | | dependents/callers 等；抽不出目标则降级 NL 定位并联 |

`auto` 检测线索（节选）：

- 代码形态（`def`/`class`/`{;`/`->`）→ similar  
- 「怎么改/经验/MR/复盘」→ pattern  
- 「谁依赖/callers/影响面」→ graph  
- 「API/公开接口」→ api（lib）  
- 否则 **NL 定位并联**：`related` + `similar` + `grep`

| 通道 | 作用 |
|------|------|
| related | exact 元数据 + 符号摘要 + 可选图谱 |
| similar | 整句 NL → 行块向量 |
| grep | 仓内全文/标识符（`ContentGrepService`：词项预编译、强命中早停，尊重忽略） |

融合优先级：`exact` > `grep` > `symbol_summary` > `codegraph`/`graph` > `line_chunk` > …

关键词抽取：英文标识符 + **中文短语**（`[\u4e00-\u9fff]{2,}`，去停用词），供 related/grep 使用。

#### pattern 文件展开

经验条目的 `relevant_files` / `anchors` 展开为带 `file_path` 的命中，与 related 文件结果在同一套 `_fuse_items` 里按通道优先级去重排序。

#### 弱结果兜底（`ResolveWeakFallback`）

仅当 intent=related 且（无结果，或 top1 非 exact 且 score&lt;0.85）时：

1. 先试附带 1 条 pattern（优先已展开的文件命中）  
2. 再试 graph dependents（以 related top 文件为种子）  

标记 `fallback=true`，不拖垮主结果。

#### 输出

`intent` / `intent_reason` / `channels_used` / `summary` / 融合 `items` / 分通道 `sections` / `channel_errors` / `index`。

---

### 4.5 pattern / graph / api（要点）

| 通道 | 关键点 |
|------|--------|
| pattern | 预筛 + extractable + 质量过滤；检索词面 rerank；resolve 侧文件展开 |
| graph | 适配层清洗；related/resolve 辅助；定义定位仍靠 exact/symbol |
| api | 独立空间；仅 lib；签名+摘要语义检索 |

### 4.6 NL→Code 检索增强（现状）

中文 / 弱英文 NL 对齐源码标识与向量时，走统一 Prep（`app/repo_analysis/services/nl2code_enhance/`）：

| 组件 | 作用 |
|------|------|
| `NlQueryPrep` | 一次准备 lexicon / 可选改写 / embed 多视角 / 关键词；`code_text` 保留原文 |
| `NlCodeQueryBuilder` | NL 多视角；`looks_like_nl` 收紧；HyDE 多语言轻量片段 |
| `RepoIdentifierLexicon` | 仓内拉丁标识；analyze/删文件后失效 |
| `NlQueryRewriter` | 可选 LLM（默认 OFF）；`weak` / `always` |
| `NlRetrievalWeakness` | 弱判定阈值 0.85（改写与 resolve 兜底共用） |

开关：`CODE_ANALYSIS_NL_TO_CODE_ENABLED`（默认 ON）、`CODE_ANALYSIS_NL_REWRITE_*`。  
resolve 将 `nl_prep` 传入 similar/related/grep，避免重复 rewrite。优化历程与五档消融见 **§5.10 / §5.12**。

---

## 5. 准度与性能优化

日期：2026-07-16 ~ 2026-07-19  
范围：分析侧吞吐 / 检索准度 / Agent 可用短列表 / NL→Code  
专项存档：`docs/superpowers/specs/`（与本文冲突时以本文与当前代码为准）

§3 / §4 描述**当前方案**；本章记录「为何如此」及**评测证据**。每节含思路、方案与实现、效果对比。末节为配置开关整体对照（符号摘要 × NL2Code）。

口径：**P** = Precision，**R** = Recall（相对 GT）；**Top1** = 首条是否命中期望定义文件。真仓默认 Pando-Agent（`PANDO_AGENT_PATH`）。

### 5.1 行块切片：行窗 + AST 符号体合并入库

#### 优化点思路

similar 仅靠固定行窗时，要么切太碎（半截函数），要么整文件进向量噪声大。需要同时覆盖「完整函数」与「非符号区碎片」，又避免同一函数被重复 embedding。

#### 优化点详细方案与实现

实现：`CodeChunkService`（`app/repo_analysis/services/codechunk/code_chunk.py`）  
调用：`FileAnalysisService._analyze_embed_phase` → `merge_chunks` → 行块向量入库。

| 切片 | 作用 | 关键参数 |
|------|------|----------|
| 行窗 `slice_file` | 覆盖非符号区；续行/括号/Python `:` 块向下扩展 | `TARGET/OVERLAP/MAX` 行 |
| 符号体 `slice_symbol_bodies` | 整段函数/小类入库 | 函数≤500 行、类≤120 行才整段 |

合并规则：`symbol_chunks` 优先；与符号行号区间重叠的行窗**丢弃**，其余保留。空文本 / 超长文本有 embedding 防护。

#### 效果对比测试

| 指标 | 说明 |
|------|------|
| 能力 | similar 可命中完整函数，也可命中顶层碎片 |
| 体积 | 重叠行窗被剔除，避免「整段 + 多个 5 行窗」重复入库 |
| 回归 | 本仓 `tests/scenarios/vector_similar/` **8/8**；Pando similar 近原文场景见 §5.2 |

---

### 5.2 similar：多视角召回 + hybrid rerank + 短列表截断

#### 优化点思路

宽召回保证 Recall，但 Agent 需要短而准的列表（尤其 Top1）。应在检索侧做多视角召回与融合 rerank，再用相对 top1 门槛截断，而不是盲目加大 `top_k`。

#### 优化点详细方案与实现

实现：`SimilarQueryNormalizer` → 多路向量 → `SimilarRerankService` → `fuse_similar_items` / `_apply_similar_trim`。

1. **多视角 query**：原文 / 去注释归一化 / 签名行；每路搜行块，按位置合并取最高向量分；`fetch_k = max(top_k×4, 40)`。  
2. **融合分**：向量 0.42 + 词元重叠 0.26 + 符号名 0.10 + 稀有 token 0.12 + 路径段 0.10；按 `file_path` 去重。  
3. **短列表**：`score ≥ top1×0.82`；同父目录最多 1 条；弱/强/极强信号软上限 3/2/1。

#### 效果对比测试（Pando，近原文 6 案）

| 阶段 | avg P | avg R | Top1 | 列表形态 |
|------|-------|-------|------|----------|
| 优化前（仅宽召回） | ~22% | 100% | 未单列（首位漂移） | 常填满 top_k≈10 |
| 多视角 + rerank | ~17.5%* | 100% | **6/6** | 更短（3～4） |
| + 短列表截断 | **100%** | **100%** | **6/6** | 多数 **n=1** |

\*截断前分母变化会导致平均 P 数字波动；对 Agent 关键的是 Top1 + 短列表。

专项：`docs/superpowers/specs/2026-07-17-similar-shortlist-precision-design.md`

---

### 5.3 similar 弱查询：稀有 token / 路径加权（Top1）

#### 优化点思路

弱改写 / 短语义 query 时纯向量易漂。不重索引、不拉长列表，仅在 rerank 抬高「稀有标识符 + 路径对齐」信号。

#### 优化点详细方案与实现

实现：`SimilarRerankService`（仅检索侧）。

- 稀有 token：长度≥6 或含 `_`，在 content 命中加分  
- 路径段：token 与 `file_path` 段/stem 重叠小幅加分  
- 略降纯向量权重，抬高 lexical / 稀有 / 路径

#### 效果对比测试（Pando，4 弱案）

| 阶段 | avg P | avg R | Top1 |
|------|-------|-------|------|
| 弱改写（未加权） | ~62% | 100% | ~2/4 |
| + 稀有 token / 路径加权 | **~88%** | **100%** | **4/4** |

强案（近原文）保持 100%。专项：`docs/superpowers/specs/2026-07-17-similar-weak-top1-design.md`

---

### 5.4 related：混合检索（exact + 符号向量）与通道收紧

#### 优化点思路

Agent「按描述/符号找位置」不能只靠向量；应用索引元数据做精确匹配并融合，同时避免把 CodeGraph 调用方当成「定义文件」主答案。

#### 优化点详细方案与实现

实现：`ExactMatchService` + `SearchService.search_related_files` / `fuse_related_*`。

| 通道 | 行为 |
|------|------|
| exact 符号 | 仅 `symbol_name` 分层打分；短词/弱词禁蹭；**路径不加符号 exact 分** |
| exact 路径 | 独立 `score_path_keyword` |
| 符号摘要向量 | related 主力语义 |
| CodeGraph | 默认**不融入**定位（`CODE_ANALYSIS_RELATED_INCLUDE_GRAPH=false`）；关系查询走 dependents/callers |

融合：exact 置顶 → 向量分 → 按路径去重 → `score ≥ top1×0.55`；有强 exact 时不硬凑满 `top_k`。  
查询返回只读 `index`（`last_scan_finished_at` / `index_age_seconds`），**查询不 sync**。

调试接口：`search chunks` / `search symbols`（人工验收，非 Agent 主路径）。

#### 效果对比测试（Pando 同 GT）

| 组合 | avg P | avg R | 解读 |
|------|-------|-------|------|
| symbol only | ~81% | 100% | 精确定位主力 |
| chunk only | ~19% | ~90% | 找定义噪声大 |
| codegraph only | ~10% | ~10% | 返回调用方，不适合作定义检索 |
| **symbol + codegraph** | **~92%** | **100%** | 最佳两两组合 |

早期宽检索全仓 `app/`：avg **P≈12% / R=100%** → 收紧 exact + 截断后核心子集曾 **P≈77% / R=100%**。  
专项：`docs/superpowers/specs/2026-07-17-p0-hybrid-related-design.md`

---

### 5.5 resolve：统一编排 + 弱结果兜底

#### 优化点思路

避免 Agent 手搓 similar/related/pattern/graph；用规则 intent 路由多通道并行融合，弱结果时有限兜底一条，不拖垮主列表。

#### 优化点详细方案与实现

实现：`SearchIntentRouter` → 并行 `_run_channel` → `_fuse_items` → `ResolveWeakFallback` → `ResolveResultPresenter`。

- `auto`：代码形态→similar；经验词→pattern；依赖词→graph；否则 **related+similar+grep** 并联  
- 融合优先级：`exact` > `grep` > `symbol_summary` > `codegraph`/`graph` > `line_chunk` …  
- 中文关键词抽取供 related/grep  
- 弱兜底（intent=related 且无结果或 top1 非 exact 且 score&lt;0.85）：先 pattern 文件命中，再 graph dependents；标记 `fallback=true`

#### 效果对比测试（Pando）

| 阶段 | 结果 |
|------|------|
| pattern 通道 bug | `intent=pattern` 失败，只剩 related |
| 修复 + 中文关键词 + pattern 文件展开 | 场景 resolve **intent+Top1** 通过（早期 3/3；现见 §5.12 全套） |

专项：`docs/superpowers/specs/2026-07-17-search-resolve-design.md`

---

### 5.6 resolve / related：主列表 `items` + `also_consider`

#### 优化点思路

mcb 与 Agent 分离，一次 CLI 几乎是全部线索。只砍短列表抬 Precision 会漏改面；应主列表保准，次层防漏。

#### 优化点详细方案与实现

实现：`ResolveResultPresenter` + `DirSiblingExpander`；related 同步分层。

| 字段 | 作用 |
|------|------|
| `items` | 高置信主列表，可带 snippet |
| `also_consider` | 同次检索多余候选 + 同目录兄弟文件，默认不带大段源码 |
| `read_hint` | 先读 items，改前扫 also_consider |

强 exact：`items` cap≤3，`also_consider`≤8；弱语义：`items` cap≤5，其余入次层。

#### 效果对比测试

| 套件 | 结果 |
|------|------|
| UT | 相关用例通过（会话内曾累计 resolve/related 场景 **19 passed**） |
| 口径 | 后续消融同时报 **items R** 与 **union R**（items∪also_consider） |

专项：`docs/superpowers/specs/2026-07-19-resolve-also-consider-design.md`

---

### 5.7 分析两阶段：embedding 快路径 / 符号摘要异步补齐

#### 优化点思路

LLM 符号摘要占满 worker 会拖慢「首次可搜」。行块入库后应立刻可 similar，摘要另抢任务补齐。

#### 优化点详细方案与实现

实现：`FileAnalysisService` 状态机。

1. **embedding 阶段**：AST → 行块向量 → `embedded`（或关摘要时直接 `completed`）  
2. **符号阶段**：另抢 `embedded` → LLM 摘要向量 → `completed`  
3. `searchable_files` = completed + embedded  

#### 效果对比测试

| 指标 | 效果 |
|------|------|
| 首次可搜 | 行块完成后即可 `search similar`，不等待全仓摘要 |
| Pando 重建 | 符号 OFF 约数分钟级完成 ~279 文件；符号 ON 需额外 LLM 时间（小时级，视 API） |

---

### 5.8 CodeGraph：已有索引走增量 sync

#### 优化点思路

每次 `analyze` 全量 `init` 图谱成本高；有 `.codegraph` 或曾成功扫描时应 `update_files`/`sync`。

#### 优化点详细方案与实现

实现：`AnalysisService` 图谱编排 + `CodeGraphGateway`。

| 条件 | 行为 |
|------|------|
| 无索引且无成功扫描历史 | `generate_graph`（≈ init） |
| 已有索引或曾有 `last_scan_finished_at` | `update_files`（≈ sync） |

适配层 `GraphResultNormalizer` 降噪；不改开源内核。查询仍不触发 sync。

#### 效果对比测试

| 套件 | 结果 |
|------|------|
| `tests/unit/test_codegraph_graph_sync.py` 等 | **15 passed**（增量路径落地时） |
| 本仓图谱场景 | 15 用例纳入综合 29/29 |

专项：`docs/superpowers/specs/2026-07-17-codegraph-incremental-analyze-design.md`

---

### 5.9 MR 经验：预筛 + 质量过滤 + 检索词面 rerank

#### 优化点思路

changelog 式经验噪声大；应用规则预筛与质量分过滤入库，检索侧词面 rerank 对弱短词即时生效（不必立刻 re-analyze）。

#### 优化点详细方案与实现

实现：`ChangeFilter` → `PatternSummarizer`（extractable 多条）→ 质量/changelog 压分 → 仅 `ready` 入向量；`search pattern` 词面 rerank。

#### 效果对比测试（Pando）

| 阶段 | ready / skipped | 向量条数 | 观感 |
|------|-----------------|----------|------|
| 旧 changelog | 13 / 0 | ≈13 | 偏 diff 复述 |
| 预筛 + extractable | 10 / 3 | ≈10 | 无价值 MR skip |
| 单 MR 多经验 | 10 / 3 | ≈29 | 更细，混运维型 |
| 质量过滤 | 10 / 3 | **≈23** | Top 偏架构决策 |

专项：`docs/superpowers/specs/2026-07-17-mr-pattern-accuracy-design.md`

---

### 5.10 NL→Code 检索增强（Prep / lexicon / 可选 LLM 改写）

#### 优化点思路

中文与弱英文 NL 难以对齐源码向量与标识符。拒绝硬编码业务别名；采用 **A（多视角 embed+形态）→ C（仓内 identifier lexicon）→ B（可选 LLM 改写）**，并由统一 Prep 门面避免重复打 LLM、避免改写覆盖原中文 query。

#### 优化点详细方案与实现

包：`app/repo_analysis/services/nl2code_enhance/`

| 组件 | 作用 |
|------|------|
| `NlToCodeEnhancement` | 总开关 `CODE_ANALYSIS_NL_TO_CODE_ENABLED`（默认 ON） |
| `NlQueryPrep` | 一次准备：lexicon / 可选改写 / embed 多视角 / 关键词扩展；`code_text` 保留原文 |
| `NlCodeQueryBuilder` | NL 多视角 embed；`looks_like_nl` 收紧（短拉丁标识不当 NL）；HyDE 多语言轻量片段 |
| `RepoIdentifierLexicon` | 从索引路径/符号抽拉丁标识；前缀桶索引；analyze/删文件后 `invalidate_repo` |
| `NlQueryRewriter` | 可选 LLM；`CODE_ANALYSIS_NL_REWRITE_*`；默认 OFF；`weak`/`always` |
| `NlRetrievalWeakness` | 统一弱判定阈值 0.85（改写触发与通道兜底共用） |

SearchService / ResolveService 共用 Prep；resolve 传 `nl_prep` 给 similar/related/grep，**不重复 rewrite**。

#### 效果对比测试

| 套件 | 结果 |
|------|------|
| `tests/unit/search/nl2code_enhance/` 等 | **84 passed**（完备性收口时） |
| 真仓六档消融 | 见 **§5.12**（17 案：D/F 94%/97%·16/17；产品默认 D；F=weak 未抬 cn_auth） |

---

### 5.11 本仓综合场景回归

#### 优化点思路

图谱 + 向量应用统一 P/R 框架，防止单点优化漂。

#### 效果对比测试

| 指标 | 数值 |
|------|------|
| 用例 | 29（图谱 15 + related 6 + similar 8） |
| 通过 | **29/29** |
| avg P / R | **~58% / ~98%** |

---

### 5.12 整体配置开关对比测试

日期：2026-07-19（17 案六档含 F/`weak`：2026-07-20）  
待测仓：Pando-Agent（`app/`）  
脚本：`python -m tests.scenarios.pando_agent.run_nl2code_ablation`  
前置：按组 `PANDO_CLEAR=1` 清库重建索引（符号 OFF 评 B/C；符号 ON 评 A/D/E）

#### 主要测试用例

resolve 用例已扩至 **17** 条（`PANDO_RESOLVE_CASES`，`ground_truth.py`），覆盖 Agent 主路径常见问法：

| 类型 | 代表 case | 查询形态 | 期望 |
|------|-----------|----------|------|
| resolve 符号 exact | `related.BaseAgent` / `PlanningAgent` / `LangGraphExecutor` / `EmbeddingModelFactory` / `OpenAIModels` / `jwt_validator` | 纯符号或路径标识 | Top1 命中定义（拉开有无符号摘要） |
| resolve 中文+符号 | `related.ReActAgent` / `ContextBuilder` | 「查找 Xxx」「Xxx」 | 命中定义文件 |
| resolve 代码 similar | `similar.think_and_act` / `agent_state` / `jwt_validator` / `websocket_endpoint` | 源码片段 | 命中对应文件 |
| resolve 弱英文 NL | `nl.semantic.memory` / `nl.semantic.websocket` | 长英文语义 | 命中 memory / websocket |
| resolve 中文 NL | `nl.cn_auth` / `cn_memory` / `cn_ws` | 「鉴权/记忆/websocket 在哪」 | 命中 auth / memory / websocket |
| related（通道对照） | `pando.full.exact.*` 等 13 条 | 关键词 | 见下表 related 列 |

口径：**avg iR** = items Recall；**avg uR** = items∪also_consider Recall；pass = items recall ≥ 用例门槛。

#### 对比场景（配置档）

| 档 | 符号摘要 embedding | NL2Code | NL_REWRITE | 含义 |
|----|-------------------|---------|------------|------|
| **A** | ON | OFF | OFF | 基线：只靠符号摘要 + 行块 |
| **B** | OFF | ON | OFF | 无摘要，开 NL 多视角/词表，不改写 |
| **C** | OFF | ON | ON（`always`） | 无摘要，NL + 每次 NL 查询 LLM 改写 |
| **D** ★产品默认 | ON | ON | OFF | 摘要 + NL，不改写（= 当前 `env.example`） |
| **E** | ON | ON | ON（`always`） | 摘要 + NL + 每次 NL 查询 LLM 改写 |
| **F** | ON | ON | ON（`weak`） | 摘要 + NL + **弱召回才** LLM 改写 |

产品默认 **D**：`CODE_ANALYSIS_SYMBOL_SUMMARY_ENABLED=true`、`CODE_ANALYSIS_NL_TO_CODE_ENABLED=true`、`CODE_ANALYSIS_NL_REWRITE_ENABLED=false`（mode 预留 `weak`）。

#### 对比效果

**Agent 主路径 resolve（17 案，含 F，2026-07-20）**

| 档 | 符号 | NL2Code | rewrite | resolve iR / uR · pass |
|----|------|---------|---------|-------------------------|
| **A** | ON | OFF | OFF | 88% / 97% · **15/17** |
| **B** | OFF | ON | OFF | 68% / 88% · **12/17** |
| **C** | OFF | ON | ON/`always` | 76% / 94% · **13/17** |
| **D** ★ | ON | ON | OFF | **94% / 97% · 16/17** |
| **E** | ON | ON | ON/`always` | 91% / 94% · **16/17** |
| **F** | ON | ON | ON/`weak` | **94% / 97% · 16/17** |

**通道对照（旧 resolve 6 案 + related 13 案）**

| 档 | resolve（旧 6） | related（13） |
|----|-----------------|---------------|
| **A** | 83% / 83% · 5/6 | **96% / 100% · 13/13** |
| **B** | 58% / 83% · 4/6 | 69% / 69% · 8/13 |
| **C** | 100% / 100% · 6/6 | 81% / 85% · 10/13 |
| **D** | 83% / 83% · 5/6 | **96% / 100% · 13/13** |
| **E** | 92% / 100% · 6/6 | **96% / 100% · 13/13** |

**焦点 NL（17 案 resolve，unionR）**

| case | A | B | C | D | E | F |
|------|---|---|---|---|---|---|
| `cn_auth` | 50% | **100%** | **100%** | 50% | **100%** | 50%（弱改写触发仍未补上） |
| `cn_memory` | **100%** | **100%** | **100%** | **100%** | **0%**（always 噪声） | **100%**（弱改写触发未伤） |
| `cn_ws` | 100% | 100% | 100% | 100% | 100% | 100% |

**结论（配置取舍）**

1. **产品默认仍 = D**：F≈D（同为 16/17、94%/97%），弱改写未抬 `cn_auth`，不必为 F 改默认。  
2. **F vs E**：F 保住 `cn_memory`（E 的 always 会带偏）；E 靠 always 补 `cn_auth`，但代价高。  
3. **`weak` 不是免费增益**：本仓 `cn_auth` 首轮弱召回后虽触发 rewrite（`rw=Y:weak`），改写种子仍不足以把鉴权文件顶进主列表。  
4. **必须开符号摘要**：无符号的 B/C（12～13/17）明显弱于有符号档。  
5. **旧 6 案上 C「全绿」不可信**；不要默认 C / 不要默认 E(`always`)。  
6. **后续若要补鉴权**：优先改 lexicon / 中文短语→路径，或专项评测 rewrite 质量，而不是默认开 always。

**第二真仓 KnowledegBase-Service（12 案 resolve，默认 D vs F，2026-07-20）**

脚本：`python -m tests.scenarios.knowledge_base.run_resolve_eval`

| 档 | rewrite | resolve iR / uR · pass |
|----|---------|-------------------------|
| **D** | OFF | 75% / 100% · **9/12** |
| **F** | weak | **92% / 100% · 11/12** |

中文 NL（unionR 均为 100%；差别在 items 主列表）：

| case | D items | F items |
|------|---------|---------|
| `cn_kb` / `cn_parse` / `cn_session` | fail（落 also） | **pass**（weak 改写抬主列表） |
| `cn_retrieval` | pass | fail（weak 偶发带偏，union 仍 100%） |

解读：第二仓上 **F 对短中文更有用**（3 个中文难例 items 从 fail→pass）；与 Pando 上 F≈D 不同，说明 weak 增益依赖仓/问法。产品默认仍可 D；难中文仓可考虑开 `NL_REWRITE=weak`。

#### 复现命令

```powershell
cd F:\Product_Dev\MOMA\Moma-CodeBase
$env:PANDO_CLEAR="1"
$env:ENABLE_INCREMENTAL_SCAN="false"
# 可选：$env:PANDO_AGENT_PATH="F:\Product_Dev\PANDO\Pando-Agent"
.\.venv\Scripts\python.exe -u -m tests.scenarios.pando_agent.run_nl2code_ablation

# 只跑 resolve 五档 / 子集：
# $env:PANDO_ABLATION_KIND="resolve"; $env:PANDO_ABLATION_ONLY="A,B,C,D,E"
# 索引已就绪：$env:PANDO_SKIP_REBUILD="1"; $env:PANDO_ABLATION_ONLY="D"
```

---

### 5.13 相关 ENV 速查

| ENV | 默认倾向 | 作用 |
|-----|----------|------|
| `CODE_ANALYSIS_LINE_CHUNK_ENABLED` | ON | 行块 / similar |
| `CODE_ANALYSIS_SYMBOL_SUMMARY_ENABLED` | **ON**（D） | 符号摘要 / related 主力 |
| `CODE_ANALYSIS_NL_TO_CODE_ENABLED` | **ON**（D） | NL 多视角 / lexicon / token 加权 |
| `CODE_ANALYSIS_NL_REWRITE_ENABLED` | **OFF**（D） | LLM 改写；难例可开 |
| `CODE_ANALYSIS_NL_REWRITE_MODE` | weak | `weak` \| `always`（勿默认 always） |
| `CODE_ANALYSIS_RELATED_INCLUDE_GRAPH` | OFF | related 是否融 CodeGraph |
| `CODE_GRAPH_ENABLED` / `PROVIDER` | ON / codegraph | 图谱 |
| `ENABLE_INCREMENTAL_SCAN` | 可配 | 后台增量扫描 |
| `PANDO_CLEAR` / `PANDO_AGENT_PATH` | 评测用 | 真仓消融重建与路径 |

## 6. 评测与复现

| 套件 | 路径 |
|------|------|
| 准确率框架 | `tests/scenarios/framework/` |
| 本仓图谱/向量 | `tests/scenarios/graph/`、`vector_similar/`、`vector_related/` |
| Pando | `tests/scenarios/pando_agent/` |
| Lib API | `tests/scenarios/lib_api/` |
| MR 经验 | `tests/scenarios/mr_experience/` |

```powershell
$env:PYTHONPATH="F:\Product_Dev\MOMA\Moma-CodeBase"
poetry run pytest tests/scenarios/pando_agent/test_similar_accuracy.py -q -s
poetry run pytest tests/scenarios/pando_agent/test_related_hybrid_accuracy.py -q -s
# 强制清空重分析：$env:PANDO_CLEAR=1
```

---

## 7. Agent 使用建议（与准度对齐）

1. **主路径** `search resolve`，少手搓多通道。  
2. **先读 `items`，改前扫 `also_consider`**：分离式对接；主列表保准（可带 snippet），次层含同目录兄弟文件防漏。  
3. 贴代码 → similar；符号/中文定位 → related；「以前怎么改」→ pattern。  
4. 改影响面 → dependents / callers，不要用 related 硬凑调用链。  
5. 索引由人工 `analyze` 就绪后再开编码任务；经验过期先 `experience analyze`。  
6. 对接方式：仅 CLI；注册 `search resolve`（见 README / `skills/mcb-resolve`），全部 `search *` 查询输出结构见 `app/cli/schemes.py` 与 `docs/cli-schemes.md`（`ok` 信封、退出码、`--timeout-ms`）。无需额外服务进程。

---

## 8. 历史细项文档

以下文件为迭代过程中的专项设计存档，**要点已并入本文**；若与本文冲突，以本文与当前代码为准：

- `docs/superpowers/specs/2026-07-16-lib-analysis-design.md`
- `docs/superpowers/specs/2026-07-16-mr-experience-design.md`
- `docs/superpowers/specs/2026-07-16-codegraph-accuracy-scenarios-design.md`
- `docs/superpowers/specs/2026-07-17-p0-hybrid-related-design.md`
- `docs/superpowers/specs/2026-07-17-similar-shortlist-precision-design.md`
- `docs/superpowers/specs/2026-07-17-similar-weak-top1-design.md`
- `docs/superpowers/specs/2026-07-17-search-resolve-design.md`
- `docs/superpowers/specs/2026-07-17-search-resolve-scenario-design.md`
- `docs/superpowers/specs/2026-07-17-agent-search-quality-design.md`
- `docs/superpowers/specs/2026-07-17-codegraph-incremental-analyze-design.md`
- `docs/superpowers/specs/2026-07-17-incremental-scan-cleanup-design.md`
- `docs/superpowers/specs/2026-07-17-inspect-cli-design.md`
- `docs/superpowers/specs/2026-07-17-mr-pattern-accuracy-design.md`
- `docs/superpowers/specs/2026-07-18-find-code-hardcase-design.md`
- `docs/superpowers/specs/2026-07-19-resolve-also-consider-design.md`

---
