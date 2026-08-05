# MomaCodeBase Design

日期：2026-07-18（章节整理：2026-07-20）  
状态：能力已落地；本文为总设计（已并入原 `docs/superpowers/specs/` 中相关方案）

**怎么读**


| 章节   | 内容                               |
| ---- | -------------------------------- |
| §1–2 | 产品定位与总体架构                        |
| §3–4 | **现状设计**：分析 / 检索怎么做（含 NL→Code）   |
| §5   | **准度与性能**：各优化点的思路、实现与评测证据（含配置消融） |
| §6–7 | 评测复现与 Agent 对接建议                 |
| §8   | 历史专项文档索引                         |


CLI 与 Agent 对接见 [README.md](README.md)。

---

## 1. 产品定位

对本地代码仓做逆向分析，形成可检索的「数字镜像」，让编码 Agent 快速拿到：

- 相似实现（给一段代码找参考）
- 相关文件 / 符号（按需求或关键词定位）
- 依赖与调用链（改动影响面）
- 历史改法经验（同类需求以前怎么改）
- Lib 公开 API（公共库接口怎么用）

**对外入口**：`mcb` CLI（交互 + 一次性命令）+ 可选 **MCP Server**（`mcb mcp serve`，stdio 查询工具）。Agent 主检索路径为 `search resolve` / MCP `resolve`。不另开 HTTP / SDK。

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


| 能力开关（ENV）                                    | 作用                                                     |
| -------------------------------------------- | ------------------------------------------------------ |
| `CODE_ANALYSIS_LINE_CHUNK_ENABLED`           | 行块 / similar 索引与检索                                     |
| `CODE_ANALYSIS_SYMBOL_SUMMARY_ENABLED`       | 符号摘要 / related 主力通道                                    |
| `CODE_GRAPH_ENABLED` / `CODE_GRAPH_PROVIDER` | 图谱；`codegraph`（默认）或 `builtin`                          |
| `MR_EXPERIENCE_ENABLED`                      | 历史经验沉淀与 `search pattern`                               |
| `CODE_ANALYSIS_NL_TO_CODE_ENABLED`           | NL→Code（多视角 / lexicon；**默认 OFF**=档位 B）                 |
| `CODE_ANALYSIS_NL_REWRITE_*`                 | 可选 LLM 改写（默认 OFF；详见 §5.13）                             |
| `ENABLE_INCREMENTAL_SCAN`                    | 文件变更重分析；新 MR 触发经验更新                                    |
| 忽略规则                                         | 扫描遵循内置排除 + 仓根 `.gitignore` + 可选 `.momaignore`          |
| `analyze status`                             | 文件计数、`index_age_seconds` / `stale_hint`、增量开关、忽略来源、最近失败 |


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


| 类型      | 解决的问题                           | 典型长度           |
| ------- | ------------------------------- | -------------- |
| 行窗滑动    | 覆盖「非符号区」、跨小段逻辑；similar 总能召回局部片段 | 默认目标约 5 行      |
| AST 符号体 | similar 命中**整段函数/类**，避免只命中窗内半截  | 函数可达数百行；小类整段入库 |


**A. 行窗切片（**`slice_file`**）**

默认参数（可用 ENV 覆盖）：


| 参数     | 默认  | ENV                                      |
| ------ | --- | ---------------------------------------- |
| 目标窗口行数 | 5   | `CODE_ANALYSIS_LINE_CHUNK_TARGET_LINES`  |
| 重叠行数   | 1   | `CODE_ANALYSIS_LINE_CHUNK_OVERLAP_LINES` |
| 扩展后上限  | 200 | `CODE_ANALYSIS_LINE_CHUNK_MAX_LINES`     |


流程：

1. 按 `target_lines` 取初步 `[start, raw_end)`。
2. `_extend_chunk_end`：向后扩行，直到满足：
  - 行续接（`\`）结束；
  - 括号 `()[]{}` 在简单扫描下平衡；
  - Python：若末行以 `:` 结尾，继续包含缩进更深的块体。
3. `_should_drop_chunk` 过滤低价值块，避免污染向量库：
  - 空白；短块且几乎全是 `import`/`package`/`#include` 等头部；
  - Python：过短 getter/setter、`@property`、仅超短 `return`；
  - Java/Go/C/C++/JS/TS/Rust：模式化 getter/setter、纯 `{`/`}` 噪音等。
4. 步进：`end - overlap`（保证前进），生成带 `start_line`/`end_line`/`text` 的 `LineTextChunk`。

**B. AST 符号体切片（**`slice_symbol_bodies`**）**

输入：同一次 AST 的 `FileInfo`。


| 符号      | 入库条件                                   | 默认上限 ENV                                               |
| ------- | -------------------------------------- | ------------------------------------------------------ |
| 函数 / 方法 | 行数 ≤ 上限，且正文 strip 后 ≥ 24 字符，且未 drop    | `CODE_ANALYSIS_SYMBOL_BODY_MAX_LINES_FUNCTION`（默认 500） |
| 类       | **仅当**行数 ≤ 类上限才整类入库；大类**不切整类**，但仍尝试其方法 | `CODE_ANALYSIS_SYMBOL_BODY_MAX_LINES_CLASS`（默认 120）    |


超限符号**跳过**（不切碎），交给行窗覆盖，避免「大类再切一遍」与行窗大量重复。

**C. 合并入库（**`merge_chunks`**）——核心规则**

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

1. 对 `FileInfo` 中符号调 LLM 生成业务向摘要（prompt：业务词 + 场景 + 检索词；少堆标识符；禁臆造）。
2. **批量调用**：同文件按 `BATCH_SIZE`（默认 6）打包一次 LLM，返回 JSON `[{id, summary}, ...]`；`CONCURRENCY` 控制并行批次数。
3. **超长/失败重试**：`context_overflow` → **折半再试**直至单条；其它 LLM/JSON 失败 → 该批回退单条；缺 id → 仅补跑缺失项。
4. **LLM 失败/空结果** → `CodeSummary.fallback_summary`（签名 + docstring/注释 + 预览），保证仍可嵌入。
5. **入库 embedding 文本**拼接：`路径 + 符号名 + 摘要`（提升 related 对路径/标识符的可召回性）。
6. **对外展示**的 `summary` 仍用摘要原文，避免把路径噪音显示给用户。
7. 写入独立 `symbol_summary` 向量空间；`search related` / `search symbols` 使用。

说明：摘要质量依赖 **re-analyze 后的新写入**；旧向量不会自动变。实现见 `SymbolBatchSummarizer`（§5.7.1）。

#### 3.1.3 CodeGraph（仓级）


| 条件                              | 行为                                               |
| ------------------------------- | ------------------------------------------------ |
| 无 `.codegraph` 且无成功扫描历史         | `generate_graph`（开源 CLI ≈ `init`）                |
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


| 状态               | 是否进向量         |
| ---------------- | ------------- |
| ready            | 是             |
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


| 场景   | CLI                                                   | 典型输入      | 主数据                  |
| ---- | ----------------------------------------------------- | --------- | -------------------- |
| 统一编排 | `search resolve`                                      | 自然语言 / 代码 | 多通道融合                |
| 相似代码 | `search similar`                                      | 代码片段      | 行块向量                 |
| 相关定位 | `search related`                                      | 关键词 / 符号名 | exact + 符号摘要 +（可选）图谱 |
| 调试   | `search chunks` / `symbols`                           | 文本        | 单通道向量                |
| 经验   | `search pattern`                                      | 需求描述      | MR 经验向量              |
| Lib  | `search api`                                          | 接口需求      | API 摘要向量             |
| 图谱   | `dependents` / `dependencies` / `callers` / `callees` | 路径或符号名    | CodeGraph            |


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


| 分量       | 权重   | 含义                                                 |
| -------- | ---- | -------------------------------------------------- |
| 向量分      | 0.42 | embedding 相似度                                      |
| 词元重叠     | 0.26 | query token ∩ content token                        |
| 符号名命中    | 0.10 | query 中抽出的 def/class 名是否出现在 content                |
| 稀有 token | 0.12 | 长度≥6 或含 `_` 的标识符命中（弱改写关键）                          |
| 路径段      | 0.10 | 稀有词与 `file_path` 段/stem 对齐（避免 session↔sessions 误伤） |


按融合分排序后 **按** `file_path` **去重**（每文件保留最高分一条）。

#### Step 3 — 短列表截断（高精度）

相对 related 更严：


| 规则           | 取值                                         |
| ------------ | ------------------------------------------ |
| 相对 top1 分数门槛 | `score ≥ top1 × 0.82`                      |
| 同父目录配额       | 每目录最多 1 条                                  |
| 信号软上限        | 弱≤3；强≤2；极强（路径 stem 命中或 symbol_score≥0.8）≤1 |


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


| 值       | 别名         | 通道                                    |
| ------- | ---------- | ------------------------------------- |
| auto    | （默认）       | 规则检测                                  |
| similar |            | similar                               |
| related | locate     | related + similar + grep（开关裁剪）        |
| pattern | experience | pattern + related                     |
| api     |            | api（仅 lib）                            |
| graph   |            | dependents/callers 等；抽不出目标则降级 NL 定位并联 |


`auto` 检测线索（节选）：

- 代码形态（`def`/`class`/`{;`/`->`）→ similar  
- 「怎么改/经验/MR/复盘」→ pattern  
- 「谁依赖/callers/影响面」→ graph  
- 「API/公开接口」→ api（lib）  
- 否则 **NL 定位并联**：`related` + `similar` + `grep`


| 通道      | 作用                                              |
| ------- | ----------------------------------------------- |
| related | exact 元数据 + 符号摘要 + 可选图谱                         |
| similar | 整句 NL → 行块向量                                    |
| grep    | 仓内全文/标识符（`ContentGrepService`：词项预编译、强命中早停，尊重忽略） |


融合优先级：`exact` > `grep` > `symbol_summary` > `codegraph`/`graph` > `line_chunk` > …

关键词抽取：英文标识符 + **中文短语**（`[\u4e00-\u9fff]{2,}`，去停用词），供 related/grep 使用。

#### pattern 文件展开

经验条目的 `relevant_files` / `anchors` 展开为带 `file_path` 的命中，与 related 文件结果在同一套 `_fuse_items` 里按通道优先级去重排序。

#### 弱结果兜底（`ResolveWeakFallback`）

仅当 intent=related 且（无结果，或 top1 非 exact 且 score<0.85）时：

1. 先试附带 1 条 pattern（优先已展开的文件命中）
2. 再试 graph dependents（以 related top 文件为种子）

标记 `fallback=true`，不拖垮主结果。

#### 输出

`intent` / `intent_reason` / `channels_used` / `summary` / 融合 `items` / 分通道 `sections` / `channel_errors` / `index`。

---



### 4.5 pattern / graph / api（要点）


| 通道      | 关键点                                               |
| ------- | ------------------------------------------------- |
| pattern | 预筛 + extractable + 质量过滤；检索词面 rerank；resolve 侧文件展开 |
| graph   | 适配层清洗；related/resolve 辅助；定义定位仍靠 exact/symbol      |
| api     | 独立空间；仅 lib；签名+摘要语义检索                              |




### 4.6 NL→Code 检索增强（现状）

中文 / 弱英文 NL 对齐源码标识与向量时，走统一 Prep（`app/repo_analysis/services/nl2code_enhance/`）：


| 组件                      | 作用                                                     |
| ----------------------- | ------------------------------------------------------ |
| `NlQueryPrep`           | 一次准备 lexicon / 可选改写 / embed 多视角 / 关键词；`code_text` 保留原文 |
| `NlCodeQueryBuilder`    | NL 多视角；`looks_like_nl` 收紧；HyDE 多语言轻量片段                 |
| `RepoIdentifierLexicon` | 仓内拉丁标识；analyze/删文件后失效                                  |
| `NlQueryRewriter`       | 可选 LLM（默认 OFF）；`weak` / `always`                       |
| `NlRetrievalWeakness`   | 弱判定阈值 0.85（改写与 resolve 兜底共用）                           |


开关：`CODE_ANALYSIS_NL_TO_CODE_ENABLED`（**默认 OFF**=B；开则为 E）、`CODE_ANALYSIS_NL_REWRITE_`*。  
resolve 将 `nl_prep` 传入 similar/related/grep，避免重复 rewrite。优化历程与七档消融见 **§5.10 / §5.12**。

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


| 切片                        | 作用                            | 关键参数                   |
| ------------------------- | ----------------------------- | ---------------------- |
| 行窗 `slice_file`           | 覆盖非符号区；续行/括号/Python `:` 块向下扩展 | `TARGET/OVERLAP/MAX` 行 |
| 符号体 `slice_symbol_bodies` | 整段函数/小类入库                     | 函数≤500 行、类≤120 行才整段    |


合并规则：`symbol_chunks` 优先；与符号行号区间重叠的行窗**丢弃**，其余保留。空文本 / 超长文本有 embedding 防护。

#### 效果对比测试


| 指标  | 说明                                                                     |
| --- | ---------------------------------------------------------------------- |
| 能力  | similar 可命中完整函数，也可命中顶层碎片                                               |
| 体积  | 重叠行窗被剔除，避免「整段 + 多个 5 行窗」重复入库                                           |
| 回归  | 本仓 `tests/scenarios/vector_similar/` **8/8**；Pando similar 近原文场景见 §5.2 |


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


| 阶段           | avg P    | avg R    | Top1      | 列表形态         |
| ------------ | -------- | -------- | --------- | ------------ |
| 优化前（仅宽召回）    | ~22%     | 100%     | 未单列（首位漂移） | 常填满 top_k≈10 |
| 多视角 + rerank | ~17.5%*  | 100%     | **6/6**   | 更短（3～4）      |
| + 短列表截断      | **100%** | **100%** | **6/6**   | 多数 **n=1**   |


截断前分母变化会导致平均 P 数字波动；对 Agent 关键的是 Top1 + 短列表。

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


| 阶段                | avg P    | avg R    | Top1    |
| ----------------- | -------- | -------- | ------- |
| 弱改写（未加权）          | ~62%     | 100%     | ~2/4    |
| + 稀有 token / 路径加权 | **~88%** | **100%** | **4/4** |


强案（近原文）保持 100%。专项：`docs/superpowers/specs/2026-07-17-similar-weak-top1-design.md`

---



### 5.4 related：混合检索（exact + 符号向量）与通道收紧



#### 优化点思路

Agent「按描述/符号找位置」不能只靠向量；应用索引元数据做精确匹配并融合，同时避免把 CodeGraph 调用方当成「定义文件」主答案。

#### 优化点详细方案与实现

实现：`ExactMatchService` + `SearchService.search_related_files` / `fuse_related_*`。


| 通道        | 行为                                                                                |
| --------- | --------------------------------------------------------------------------------- |
| exact 符号  | 仅 `symbol_name` 分层打分；短词/弱词禁蹭；**路径不加符号 exact 分**                                   |
| exact 路径  | 独立 `score_path_keyword`                                                           |
| 符号摘要向量    | related 主力语义                                                                      |
| CodeGraph | 默认**不融入**定位（`CODE_ANALYSIS_RELATED_INCLUDE_GRAPH=false`）；关系查询走 dependents/callers |


融合：exact 置顶 → 向量分 → 按路径去重 → `score ≥ top1×0.55`；有强 exact 时不硬凑满 `top_k`。  
查询返回只读 `index`（`last_scan_finished_at` / `index_age_seconds`），**查询不 sync**。

调试接口：`search chunks` / `search symbols`（人工验收，非 Agent 主路径）。

#### 效果对比测试（Pando 同 GT）


| 组合                     | avg P    | avg R    | 解读             |
| ---------------------- | -------- | -------- | -------------- |
| symbol only            | ~81%     | 100%     | 精确定位主力         |
| chunk only             | ~19%     | ~90%     | 找定义噪声大         |
| codegraph only         | ~10%     | ~10%     | 返回调用方，不适合作定义检索 |
| **symbol + codegraph** | **~92%** | **100%** | 最佳两两组合         |


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
- 弱兜底（intent=related 且无结果或 top1 非 exact 且 score<0.85）：先 pattern 文件命中，再 graph dependents；标记 `fallback=true`



#### 效果对比测试（Pando）


| 阶段                        | 结果                                                |
| ------------------------- | ------------------------------------------------- |
| pattern 通道 bug            | `intent=pattern` 失败，只剩 related                    |
| 修复 + 中文关键词 + pattern 文件展开 | 场景 resolve **intent+Top1** 通过（早期 3/3；现见 §5.12 全套） |


专项：`docs/superpowers/specs/2026-07-17-search-resolve-design.md`

---



### 5.6 resolve / related：主列表 `items` + `also_consider`



#### 优化点思路

mcb 与 Agent 分离，一次 CLI 几乎是全部线索。只砍短列表抬 Precision 会漏改面；应主列表保准，次层防漏。

#### 优化点详细方案与实现

实现：`ResolveResultPresenter` + `DirSiblingExpander`；related 同步分层。


| 字段              | 作用                          |
| --------------- | --------------------------- |
| `items`         | 高置信主列表，可带 snippet           |
| `also_consider` | 同次检索多余候选 + 同目录兄弟文件，默认不带大段源码 |
| `read_hint`     | 先读 items，改前扫 also_consider  |


强 exact：`items` cap≤3，`also_consider`≤8；弱语义：`items` cap≤5，其余入次层。

#### 效果对比测试


| 套件  | 结果                                                     |
| --- | ------------------------------------------------------ |
| UT  | 相关用例通过（会话内曾累计 resolve/related 场景 **19 passed**）        |
| 口径  | 后续消融同时报 **items R** 与 **union R**（items∪also_consider） |


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


| 指标       | 效果                                                 |
| -------- | -------------------------------------------------- |
| 首次可搜     | 行块完成后即可 `search similar`，不等待全仓摘要                   |
| Pando 重建 | 符号 OFF 约数分钟级完成 ~279 文件；符号 ON 需额外 LLM 时间（小时级，视 API） |


---



### 5.7.1 符号摘要：批量 LLM + 超长折半重试



#### 优化点思路

符号摘要原先「一符号一次 LLM」，大仓耗时长。改为同文件批量打包可显著降 round-trip；大函数连批可能撑爆上下文，故在 LLM 返回超长失败时折半重试，而不是整文件失败。

#### 优化点详细方案与实现

实现：`SymbolBatchSummarizer`（`codesummary/batch_summarizer.py`），由 `CodeVectorService.vectorize_and_store_symbol_summaries` 调用。


| 步骤    | 行为                                                         |
| ----- | ---------------------------------------------------------- |
| 打包    | 按 `BATCH_SIZE`（默认 6）切批                                     |
| 调用    | 一批一次 `chat_stream`，要求 JSON `[{id, summary}, ...]`          |
| 超长    | 识别 `context_overflow` / context length 类错误 → **折半再试**，直至单条 |
| 其它失败  | JSON 坏 / 非超长 LLM 错 → 该批回退单条 `CodeSummary.llm_summarize`    |
| 缺 id  | 保留已解析项，仅对缺失补跑单条                                            |
| 单条仍失败 | `fallback_summary` 确定性文案，保证可嵌入                             |


配置：

- `CODE_ANALYSIS_SYMBOL_SUMMARY_LLM_BATCH_SIZE`
- `CODE_ANALYSIS_SYMBOL_SUMMARY_LLM_CONCURRENCY`（并行批次数）



#### 效果对比测试


| 指标     | 效果                                                                                                 |
| ------ | -------------------------------------------------------------------------------------------------- |
| LLM 次数 | 理想约 `ceil(N / BATCH_SIZE)`；超长时折半，介于批量与逐条之间                                                         |
| UT     | `tests/unit/codesummary/test_symbol_batch_summarize.py`（成功批量 / 坏 JSON 回退 / 缺 id / **overflow 折半**） |
| 功能     | `tests/functional/codesummary/test_symbol_batch_summarize_flow.py`（贯通入库路径）                         |


---



### 5.8 CodeGraph：已有索引走增量 sync



#### 优化点思路

每次 `analyze` 全量 `init` 图谱成本高；有 `.codegraph` 或曾成功扫描时应 `update_files`/`sync`。

#### 优化点详细方案与实现

实现：`AnalysisService` 图谱编排 + `CodeGraphGateway`。


| 条件                              | 行为                       |
| ------------------------------- | ------------------------ |
| 无索引且无成功扫描历史                     | `generate_graph`（≈ init） |
| 已有索引或曾有 `last_scan_finished_at` | `update_files`（≈ sync）   |


适配层 `GraphResultNormalizer` 降噪；不改开源内核。查询仍不触发 sync。

#### 效果对比测试


| 套件                                          | 结果                     |
| ------------------------------------------- | ---------------------- |
| `tests/unit/test_codegraph_graph_sync.py` 等 | **15 passed**（增量路径落地时） |
| 本仓图谱场景                                      | 15 用例纳入综合 29/29        |


专项：`docs/superpowers/specs/2026-07-17-codegraph-incremental-analyze-design.md`

---



### 5.9 MR 经验：预筛 + 质量过滤 + 检索词面 rerank



#### 优化点思路

changelog 式经验噪声大；应用规则预筛与质量分过滤入库，检索侧词面 rerank 对弱短词即时生效（不必立刻 re-analyze）。

#### 优化点详细方案与实现

实现：`ChangeFilter` → `PatternSummarizer`（extractable 多条）→ 质量/changelog 压分 → 仅 `ready` 入向量；`search pattern` 词面 rerank。

#### 效果对比测试（Pando）


| 阶段               | ready / skipped | 向量条数    | 观感          |
| ---------------- | --------------- | ------- | ----------- |
| 旧 changelog      | 13 / 0          | ≈13     | 偏 diff 复述   |
| 预筛 + extractable | 10 / 3          | ≈10     | 无价值 MR skip |
| 单 MR 多经验         | 10 / 3          | ≈29     | 更细，混运维型     |
| 质量过滤             | 10 / 3          | **≈23** | Top 偏架构决策   |


专项：`docs/superpowers/specs/2026-07-17-mr-pattern-accuracy-design.md`

---



### 5.10 NL→Code 检索增强（Prep / lexicon / 可选 LLM 改写）



#### 优化点思路

中文与弱英文 NL 难以对齐源码向量与标识符。拒绝硬编码业务别名；采用 **A（多视角 embed+形态）→ C（仓内 identifier lexicon）→ B（可选 LLM 改写）**，并由统一 Prep 门面避免重复打 LLM、避免改写覆盖原中文 query。

#### 优化点详细方案与实现

包：`app/repo_analysis/services/nl2code_enhance/`


| 组件                      | 作用                                                         |
| ----------------------- | ---------------------------------------------------------- |
| `NlToCodeEnhancement`   | 总开关 `CODE_ANALYSIS_NL_TO_CODE_ENABLED`（**默认 OFF**=A）       |
| `NlQueryPrep`           | 一次准备：lexicon / 可选改写 / embed 多视角 / 关键词扩展；`code_text` 保留原文   |
| `NlCodeQueryBuilder`    | NL 多视角 embed；`looks_like_nl` 收紧（短拉丁标识不当 NL）；HyDE 多语言轻量片段   |
| `RepoIdentifierLexicon` | 从索引路径/符号抽拉丁标识；前缀桶索引；analyze/删文件后 `invalidate_repo`         |
| `NlQueryRewriter`       | 可选 LLM；`CODE_ANALYSIS_NL_REWRITE_*`；默认 OFF；`weak`/`always` |
| `NlRetrievalWeakness`   | 统一弱判定阈值 0.85（改写触发与通道兜底共用）                                  |


SearchService / ResolveService 共用 Prep；resolve 传 `nl_prep` 给 similar/related/grep，**不重复 rewrite**。

#### 效果对比测试


| 套件                                     | 结果                                                                       |
| -------------------------------------- | ------------------------------------------------------------------------ |
| `tests/unit/search/nl2code_enhance/` 等 | **84 passed**（完备性收口时）                                                    |
| 真仓七档消融                                 | 见 **§5.12**（九仓：Pando/KB/Go/Django/HCL/NNG/spdlog/Gson/Express；**产品默认 B**） |


---



### 5.11 本仓综合场景回归



#### 优化点思路

图谱 + 向量应用统一 P/R 框架，防止单点优化漂。

#### 效果对比测试


| 指标        | 数值                                |
| --------- | --------------------------------- |
| 用例        | 29（图谱 15 + related 6 + similar 8） |
| 通过        | **29/29**                         |
| avg P / R | **~58% / ~98%**                   |


---



### 5.12 整体配置开关对比测试（九仓 + 本仓 related）

日期：**2026-07-27**（七仓 **CLEAR 重分析** + A–G：HCL / spdlog / Express / Gson / NNG / **Pando / KB**；对比稿 `tests/output/_reanalyze_ag_queue_compare.md`；队列脚本 `tests.scenarios.mid_oss.run_reanalyze_ag_queue`）。  
前序：**2026-07-25** items 排序 + relevance v2（`_nine_repo_befg_before_after.md`）。  
下表 **HCL / spdlog / NNG / Gson / Express / Pando / KB = 重分析后 A–G**；Go / Django 仍为 07-25 排序优化后（A/C/D 含更早基线）。Go CLEAR 已中止，未写入新数。  
¶ HCL **D** 跑次中 1 例因嵌入 API DNS 失败记 ERROR，按失败计入 19/32。

**档位重标号（相对旧版）**：旧 G→**A**，旧 A→**B**，旧 B→**C**，旧 C→**D**，旧 D→**E**，旧 E→**F**，旧 F→**G**。

九仓 resolve 消融共用七档 **A–G**：


| 档           | 符号摘要 | NL2Code | NL_REWRITE   | 短标签          |
| ----------- | ---- | ------- | ------------ | ------------ |
| **A**       | OFF  | OFF     | OFF          | 仅Chunk        |
| **B** ★产品默认 | ON   | OFF     | OFF          | 符号           |
| **C**       | OFF  | ON      | OFF          | NL           |
| **D**       | OFF  | ON      | ON（`always`） | NL+always    |
| **E**       | ON   | ON      | OFF          | 符号+NL        |
| **F**       | ON   | ON      | ON（`always`） | 符号+NL+always |
| **G**       | ON   | ON      | ON（`weak`）   | 符号+NL+weak   |


口径：**pass** = items recall ≥ 用例门槛（数量优先）；**avg iR** = items Recall；**avg uR** = items∪also_consider Recall；单元格格式 **pass/total · iR%/uR%**；**avg_ms** = 单次 resolve 墙钟均值。  
产品默认 **B**：符号 ON + NL2Code OFF + rewrite OFF。完整对比表、仓内①–⑦排序、纯中文 B/E 专项与**选型逻辑**见下文。

#### Agent 向用例配比（目标）


| 类型             | 目标占比   | 说明         |
| -------------- | ------ | ---------- |
| 纯符号 `sym`      | 25–30% | 栈迹 / 标识符   |
| 符号+NL `sym_nl` | 15–20% | Agent 混合问法 |
| 纯 NL `nl`      | 30–35% | 中/英文意图     |
| 代码片段 `similar` | 15–20% | 贴代码找同类     |
| 难例 `hard`      | 10–15% | 同名歧义 / 短中文 |



| 仓                         | 主要语言 | 角色          | 分析范围                         | resolve/related 案数                 | 档位覆盖       | 脚本                                                 |
| ------------------------- | ---- | ----------- | ---------------------------- | ---------------------------------- | ---------- | -------------------------------------------------- |
| **Pando-Agent**           | Python | 业务 Agent 真仓 | `app/`                       | **22** resolve                     | A–G        | `tests.scenarios.pando_agent.run_nl2code_ablation` |
| **KnowledegBase-Service** | Python | 第二业务真仓      | 全仓 `app/` 等                  | **17** resolve                     | A–G        | `tests.scenarios.knowledge_base.run_resolve_eval`  |
| **Go（开源）**                | Go | 大仓多包        | `src` 下 net+encoding+context | **32** resolve                     | A–G        | `tests.scenarios.go_oss.run_resolve_eval`          |
| **Django（开源）**            | Python | 大仓整包        | `django/`                    | **33** resolve                     | A–G        | `tests.scenarios.django_oss.run_resolve_eval`      |
| **HCL（开源）**               | Go | 中型 Go 库     | 全仓                           | **32** resolve                     | A–G        | `tests.scenarios.hcl_oss` / `mid_oss.run_be_eval`  |
| **NNG（开源）**               | C | 中型 C 库      | 全仓                           | **32** resolve                     | A–G        | `tests.scenarios.nng_oss` / `mid_oss.run_be_eval`  |
| **spdlog（开源）**            | C++ | 中型 C++ 头库   | 全仓                           | **32** resolve                     | A–G        | `tests.scenarios.spdlog_oss` / `mid_oss.run_be_eval` |
| **Gson（开源）**              | Java | 中型 JSON 库   | `gson/src/main/java`         | **32** resolve                     | A–G        | `tests.scenarios.gson_oss` / `mid_oss.run_be_eval` |
| **Express（开源）**           | JS | 小型 Web 框架核  | 全仓 `lib/`（约 7 文件）            | **32** resolve                     | A–G        | `tests.scenarios.express_oss` / `mid_oss.run_be_eval` |
| **本仓 Moma-CodeBase**      | Python | 框架回归        | 本仓 `app/`                    | **11** related（+ similar/graph 另计） | related 场景 | `tests.scenarios.vector_related` 等                 |


GT：`*/ground_truth.py`；`extra.case_kind` ∈ `{sym,sym_nl,nl,similar,hard}`。中型开源仓配比均为 sym8 / sym_nl6 / nl10 / similar5 / hard3。

#### 九仓结果总表（resolve）

仓内效果序（同仓 A–G）：主序 **pass**，同 pass 比 **avg iR**，再比 **avg uR**；并列则按档位字母。单元格末尾 **①最好 → ⑦最弱**。


| 档       | 短标签          | Pando 22          | KB 17              | Go 32†            | Django 33         | HCL 32            | NNG 32            | spdlog 32§        | Gson 32           | Express 32‡       |
| ------- | ------------ | ----------------- | ------------------ | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- |
| **A**   | 仅Chunk        | 15/22 · 68%/86% ⑦ | 6/17 · 35%/76% ⑦   | 7/32 · 19%/56% ⑦  | 8/33 · 24%/64% ⑦  | 13/32 · 34%/59% ⑦  | 22/32 · 43%/62% ⑦ | 16/32 · 31%/47% ⑥  | 25/32 · 70%/94% ②  | 29/32 · 86%/98% ⑤ |
| **B** ★ | 符号           | 19/22 · 86%/93% ③ | 13/17 · 76%/88% ④  | 20/32 · 58%/89% ④ | 27/33 · 82%/95% ① | 21/32 · 56%/78% ④ | 28/32 · 57%/81% ① | 24/32 · 48%/78% ① | 29/32 · 83%/95% ① | 32/32 · 94%/100% ② |
| **C**   | NL           | 17/22 · 75%/100% ⑥ | 15/17 · 88%/94% ①  | 11/32 · 31%/58% ⑥ | 14/33 · 40%/78% ⑤ | 18/32 · 48%/55% ⑥ | 24/32 · 52%/66% ④ | 19/32 · 38%/52% ② | 24/32 · 67%/94% ③ | 29/32 · 84%/98% ⑥ |
| **D**   | NL+always    | 18/22 · 80%/95% ⑤ | 13/17 · 76%/82% ⑥  | 14/32 · 39%/66% ⑤ | 12/33 · 36%/68% ⑥ | 19/32 · 53%/66% ⑤¶ | 23/32 · 49%/70% ⑤ | 15/32 · 31%/53% ⑦ | 22/32 · 64%/93% ⑤ | 28/32 · 86%/98% ⑦ |
| **E**   | 符号+NL        | 21/22 · 95%/98% ① | 13/17 · 76%/88% ⑤  | 22/32 · 61%/80% ② | 24/33 · 73%/95% ③ | 24/32 · 60%/80% ③ | 25/32 · 54%/72% ② | 19/32 · 34%/70% ③ | 22/32 · 62%/91% ⑥ | 32/32 · 94%/100% ③ |
| **F**   | 符号+NL+always | 19/22 · 84%/86% ④ | 13/17 · 76%/94% ③  | 23/32 · 66%/84% ① | 22/33 · 65%/97% ④ | 27/32 · 69%/86% ① | 22/32 · 51%/66% ⑥ | 18/32 · 33%/66% ⑤ | 23/32 · 64%/91% ④ | 32/32 · 97%/98% ① |
| **G**   | 符号+NL+weak   | 21/22 · 93%/95% ② | 13/17 · 76%/100% ② | 21/32 · 58%/73% ③ | 25/33 · 74%/94% ② | 26/32 · 66%/81% ② | 24/32 · 54%/72% ③ | 18/32 · 33%/67% ④ | 22/32 · 62%/91% ⑦ | 31/32 · 91%/100% ④ |


仓内效果序一览：


| 仓       | ①   | ②   | ③   | ④   | ⑤   | ⑥   | ⑦   |
| ------- | --- | --- | --- | --- | --- | --- | --- |
| Pando   | E   | G   | B   | F   | D   | C   | A   |
| KB      | C   | G   | F   | B   | E   | D   | A   |
| Go      | F   | E   | G   | B   | D   | C   | A   |
| Django  | B   | G   | E   | F   | C   | D   | A   |
| HCL     | F   | G   | E   | B   | D   | C   | A   |
| NNG     | B   | E   | G   | C   | D   | F   | A   |
| spdlog  | B   | C   | E   | G   | F   | A   | D   |
| Gson    | B   | A   | C   | F   | D   | E   | G   |
| Express | F   | B   | E   | G   | A   | C   | D   |


（口径：pass · avg iR / avg uR。HCL/spdlog/NNG/Gson/Express/Pando/KB = **CLEAR 重分析**后 A–G（07-26/07-27）；Go/Django = **2026-07-25** 排序优化后含 relevance v2；其余见脚注。）  
† Go：**net/encoding/context** 三包子集；本轮 CLEAR 已中止，表内仍为排序后旧数。  
‡ Express：核心仅约 **7** 个 `.js`，极小仓；重分析后 B/E **32/32 · 94%/100%**，F **32/32 · 97%/98%**，G **31/32 · 91%/100%**。  
§ spdlog：新摘要 prompt **CLEAR 重分析**后全档复测；A/C–G 相对旧 Design 均有提升，B pass 持平 24/32。  
¶ HCL D：过夜跑次中 1 例 SiliconFlow DNS 失败，按失败计入。

#### 九仓档位平均耗时（ms / 次 resolve）

仓内速度序：**①最快 → ⑦最慢**（数字越小越好）。


| 档       | Pando  | KB     | Go     | Django | HCL    | NNG    | spdlog | Gson   | Express |
| ------- | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------- |
| **A**   | ① 20k  | ① 4.0k | ① 6.6k | ① 6.2k | ① 4.4k | ① 5.9k | ② 6.5k | ① 4.9k | ① 2.7k  |
| **B** ★ | ③ 29k  | ③ 19k  | ③ 18k  | ③ 19k  | ③ 9.3k | ③ 9.2k | ④ 11k  | ③ 24k  | ④ 13k   |
| **C**   | ④ 34k  | ② 4.5k | ② 14k  | ② 11k  | ② 9.3k | ④ 13k  | ① 4.5k | ② 8.1k | ③ 5.8k  |
| **D**   | ⑥ 121k | ⑤ 32k  | ⑦ 95k  | ⑥ 58k  | ⑥ 56k  | ⑦ 87k  | ⑦ 48k  | ⑥ 61k  | ⑦ 64k   |
| **E**   | ② 29k  | ④ 21k  | ④ 24k  | ④ 23k  | ④ 16k  | ② 8.2k | ③ 10k  | ④ 25k  | ② 5.1k  |
| **F**   | ⑦ 162k | ⑦ 138k | ⑥ 69k  | ⑦ 68k  | ⑦ 82k  | ⑥ 68k  | ⑥ 42k  | ⑦ 68k  | ⑥ 49k   |
| **G**   | ⑤ 66k  | ⑥ 51k  | ⑤ 28k  | ⑤ 49k  | ⑤ 17k  | ⑤ 38k  | ⑤ 24k  | ⑤ 26k  | ⑤ 32k   |


仓内速度序一览：


| 仓       | ①最快 | ②   | ③   | ④   | ⑤   | ⑥   | ⑦最慢 |
| ------- | --- | --- | --- | --- | --- | --- | --- |
| Pando   | A   | E   | B   | C   | G   | D   | F   |
| KB      | A   | C   | B   | E   | D   | G   | F   |
| Go      | A   | C   | B   | E   | G   | F   | D   |
| Django  | A   | C   | B   | E   | G   | D   | F   |
| HCL     | A   | C   | B   | E   | G   | D   | F   |
| NNG     | A   | E   | B   | C   | G   | F   | D   |
| spdlog  | C   | A   | E   | B   | G   | F   | D   |
| Gson    | A   | C   | B   | E   | G   | D   | F   |
| Express | A   | E   | C   | B   | G   | F   | D   |


每用例 × 档位耗时见：`tests/output/.tmp_{hcl,nng,spdlog,gson,express,pando,kb}_ablation_newgt.md` / `.tmp_{go,django}_ablation_8b_adefg.md`。

#### B vs E 专项（决定默认值）

争议点：总表上部分仓 E（符号+NL）略高于或接近 B，是否应默认 E？对中国区是否必须开 NL2Code？

**1）按** `case_kind` **看 B/E（pass）**（前四仓沿用 07-22 分型；中型三仓为 07-24）


| 仓          | nl / hard 向结论 |
| ---------- | ------------- |
| Pando / KB | CLEAR 后 Pando E/G ①（21/22），B 19/22；KB C ①（15/17），B 13/17（相对旧 +1） |
| Go         | E 略好（22 vs 20；优化后） |
| Django     | 优化后 B 仍略好于 E（25 vs 24）；F 不稳 |
| HCL        | 重分析后 **E 好于 B**（24 vs 21）；F/G 更高但仍慢 |
| NNG        | 重分析后 **B①**（28 vs E 25）；B 的 iR/uR 更好 |
| spdlog     | 重分析后 **B 仍①**（24/32）；E 19/32，B 更稳 |
| Gson       | 重分析后 **B 仍明显更好**（29 vs E 22；A 亦升至 25） |
| Express    | 重分析后 B=E=32/32，G 31/32；极小仓特例 |


→ 分类型 / 跨仓后 **没有稳定的「E 系统性优于 B」**；Java Gson / C++ spdlog / C NNG 上 B 更稳。HCL 重分析后 E/F/G 抬升，仍不改默认 B（延迟）。

**2）纯中文子集（无拉丁字母，中国区最相关）**

前四仓合计 **19** 条纯中文：


| 指标                   | B         | E         |
| -------------------- | --------- | --------- |
| pass                 | **10/19** | **10/19** |
| pass 翻转（E 多过 / B 多过） | —         | **0 / 0** |


仅 2 条出现 **uR** 软差异（答案进 `also_consider`，仍不算 pass）：KB `文档解析在哪`、Django `用户认证在哪`。  
→ **以 items/pass 为准，纯中文上对比不出 B、E 效果差**；NL2Code（E 相对 B 多开的部分）**没有把这些中文问抬进 items**。

中型开源仓纯 NL 上 B 仍可偏弱（答案常进 also_consider）；HCL 重分析后 E **+3 pass vs B**，Gson/spdlog/NNG 上 E 仍不如 B。

**3）延迟**

多数仓速度序上 B 不慢于 E；F/G/D 因 LLM 改写可再慢一个数量级。A（仅 Chunk）最快但准度最差。

**4）F 慢的原因（排除作默认）**

`rewrite_mode=always` → 凡 `looks_like_nl` **先打一轮 LLM 改写再检索**，再叠加更多 embed 视角；墙钟常到几十秒～数分钟。G（weak）仅弱召回才改写，仍明显贵于 B/E。Express 极小仓上 F 可满分，但仍慢一个数量级，不改默认结论。

#### 产品默认选型逻辑（2026-07-23 起 = **B**；07-25 排序 + 07-26/07-27 七仓 CLEAR 后仍成立）

决策顺序：

1. **先保证符号通道**：仅 Chunk 的 A 与无符号的 C/D 在多数仓上仍弱于 B → 默认必须 **symbol ON**（排除 A/C/D）。重分析后 A–B 差距明显收窄（表征变好）；CLEAR 仓上 **B pass 仍全高于 A**。例外：KB 的 C、重分析后 Gson 的 A 可冲高，但不跨仓稳定压过 B。
2. **在有符号的 B/E/F/G 中比收益/成本**：
  - F：Express/Go/HCL 可①，但延迟常末档；Django/Gson/NNG/Pando 上 F 不稳或回退 → **不默认**。  
  - G：延迟远高于 B/E；KB G 本轮 CLEAR **−1** → **不默认**；难例可开。  
  - E vs B：总表接近或互有胜负；**Gson/NNG/spdlog/Django/Express/KB 上 B 不差于 E**；HCL/Pando 上 E 可更高但仍慢 → **不默认开 NL2Code**。
3. **落点 B**：`SYMBOL_SUMMARY=ON` + `NL_TO_CODE=OFF` + `NL_REWRITE=OFF`。
4. **可选增强**：业务仓确认中文/意图难例收益 > 延迟时，再开 E；弱改写开 G；勿默认 always（F）。
5. **items 排序 + 摘要重分析保留**：排序 v2 跨仓净正；CLEAR 仓多数档抬升；默认 B 开源五仓净 **+3 pass**，Pando/KB 合计持平。

配置映射：


| 档         | `SYMBOL_SUMMARY` | `NL_TO_CODE` | `NL_REWRITE` / mode |
| --------- | ---------------- | ------------ | ------------------- |
| **B ★默认** | true             | **false**    | false / —           |
| E 可选      | true             | true         | false / —           |
| G 可选      | true             | true         | true / weak         |
| F 不推荐默认   | true             | true         | true / always       |
| A 基线对比    | false            | false        | false / —           |


落地文件：`app/config/settings.py`（字段默认）、`env` / `env.example`、本文 §5.13。

#### 九仓交叉结论（新 GT）

1. **必须开符号（常规仓）**：A 仍多弱于 B；重分析后 A 大幅抬升、A–B 差距收窄，但 CLEAR 仓上 B 仍全面高于 A。Gson/Django/NNG/spdlog/Express 上 B 为仓内①或②。
2. **产品默认 = B**：见上节选型逻辑；NL2Code（E）与 LLM 改写（G/F）作可选。Gson 重分析后 B≫E（**29 vs 22**）进一步支持默认不开 NL；业务仓 Pando B −1 / KB B +1，合计持平。
3. **仓内效果序不一**：Go/Express/HCL 偏 F；KB 偏 **C**（CLEAR 后）；NNG/spdlog/Django/Gson 偏 **B**；Pando 偏 **E/G**——跨仓没有「唯一最优档」。Express 重分析后 B/E/F 满分 pass（G 31/32）。HCL 序 **F>G>E>B**；Gson 重分析后序变为 **B>A>C>F>…**；Pando **E>G>B>…**；KB **C>G>F>B>…**。
4. **语言覆盖**：已含 Python / Go / C / C++ / **Java** / **JS**。Java（Gson）重分析后 B **29/32 · 83%/95%**；极小 JS 仓（Express）不宜外推到大型前端仓。
5. **耗时**：D/F（always 改写）仍可到 40–80s+/次（本轮 Pando/KB 的 F 更高）；消融用 `RESOLVE_CHANNEL_TIMEOUT_MS=0`，日常 Agent 建议有限超时（如 120s）。
6. **items 排序：建议保留**（含 relevance 收紧 v2）：Express/Gson 大幅升，HCL/NNG/Go 小升；Django B 由一度 −3 收至 **−1**（uR 仍高，答案多在 also_consider）；F/G 回退另含 always/weak 改写抖动。不整段回退。
7. **摘要 CLEAR 重分析（七仓，2026-07-26～07-27）**：HCL/spdlog/Express/Gson/NNG/Pando/KB 多数档抬升或持平；弱档 A/C 受益最大；默认 B 开源五仓净 **+3**，业务两仓合计 0。详见下节「七仓 CLEAR 重分析」对比表。Go/Django 尚未本轮 CLEAR。

#### items 主列表排序优化（2026-07-24 改动；2026-07-25 B/E/G/F 复测 + relevance v2）

**背景**：多仓出现 **uR 高、iR/pass 偏低**——正确答案已在融合池 / `also_consider`，但 `ResolveResultPresenter` 对外 **Top3 items** 被伞文件、测试路径或弱相关 exact 噪声占满（Express / Go / Gson-NL 最典型）。

**改动**（检索端，不增通道、不改默认 B 开关；**禁止仓名/评测特化**）：

| 项 | 说明 |
| --- | --- |
| 实现 | `app/repo_analysis/services/search_resolve/result_presenter.py`；`resolve` 传入 `query` 参与切分 |
| 查询相关性 | 拆 **strong / weak**：符号全名与文件名 stem 为强信号；路径段精确命中与驼峰片段为弱信号（禁止静态业务/项目别名词表） |
| 档位抬升 | **仅 strong** 可抬 band；文件名允许 `app→application` 前缀，**路径目录禁止** `model⊂models` 蹭分 |
| 噪声惩罚 | 测试/`vendor` 降权；伞文件（`main`/`index`/`base` 等）**仅浅路径**重罚，深路径基类实现不误伤 |
| 同族去重 | `*-inl` / `*_impl` 等同实现族主列表只留一条 |

**摘要 prompt（分析端）**：去掉「鉴权/会话/缓存」等业务套话示例，改为贴合源码真实职责（`code_summary.py` / `api_summary.py`）。已入库摘要需 **re-analyze** 才生效。**2026-07-26～07-27** 已对 **HCL / spdlog / Express / Gson / NNG / Pando / KB** CLEAR 重分析并复测 A–G；Go / Django 仍为重分析前索引（Go CLEAR 曾中止）。

**七仓默认 B 前后对比**（改前 = 排序优化前 A–G 中 B 行；改后 = 07-24 `skip_rebuild` 只跑 B；脚本 `tests.scenarios.mid_oss.run_b_before_after`；明细 `tests/output/_seven_repo_b_before_after.md`）：


| 仓 | Before pass · iR/uR | After pass · iR/uR | Δ pass |
| --- | --- | --- | --- |
| Go | 20/32 · 58%/89% | 20/32 · 58%/89% | 0 |
| Django | 28/33 · 85%/98% | 27/33 · 82%/98% | −1 |
| HCL | 21/32 · 58%/77% | 23/32 · 61%/77% | +2 |
| NNG | 24/32 · 55%/80% | 25/32 · 54%/80% | +1 |
| spdlog | 18/32 · 41%/71% | 24/32 · 45%/76% | **+6** |
| Gson | 24/32 · 72%/90% | 28/32 · 82%/95% | **+4** |
| Express | 21/32 · 64%/100% | **32/32 · 94%/100%** | **+11** |


> 注：07-25 排序 v2 三仓 B 复核：Django **27/33 · 82%/95%**、Gson **27/32 · 80%/94%**、Express **32/32 · 94%/100%**。**07-26～07-27** 七仓 CLEAR 重分析后 A–G 已写入总表与下节对比（Gson B **29/32**、NNG B **28/32**、Pando B **19/22**、KB B **13/17** 等）。

##### 本轮优化前后对比（2026-07-25；含 relevance 收紧 v2）

改前：§5.12 排序优化前 A–G 快照；改后：`skip_rebuild` 重跑（`ResolveResultPresenter` 排序 + strong/weak relevance）。  
档位：B=符号 · E=符号+NL · G=符号+NL+weak · F=符号+NL+always。  
指标：pass · iR/uR（如 27/32 · 80%/94%）。  
脚本：`tests.scenarios.mid_oss.run_befg_before_after`；明细：`tests/output/_nine_repo_befg_before_after.md`；三仓 B 复核：`_befg_deg_b_v2.txt`。  
**HCL / spdlog After**（本表历史列）= 排序前基线 → 重分析后；**NNG / Gson / Express** 重分析数见下一节。  
**决策：保留本轮排序优化（含 v2）**；七仓 CLEAR 重分析已写入总表。

###### 档位 B

| 仓 | Before | After | Δ |
| --- | --- | --- | --- |
| pando | 19/22 · 86%/91% | 20/22 · 91%/91% | iR +5% · uR -0% · pass +1 |
| kb | 12/17 · 71%/88% | 12/17 · 71%/88% | iR -0% · uR +0% · pass 0 |
| go | 20/32 · 58%/89% | 20/32 · 58%/89% | iR -0% · uR +0% · pass 0 |
| django | 28/33 · 85%/98% | **27/33 · 82%/95%** | iR -3% · uR -3% · pass -1 |
| hcl | 21/32 · 58%/77% | **21/32 · 56%/78%** | iR -2% · uR +1% · pass 0 |
| nng | 24/32 · 55%/80% | **25/32 · 56%/81%** | iR +1% · uR +1% · pass +1 |
| spdlog | 18/32 · 41%/71% | **24/32 · 48%/78%** | iR +7% · uR +7% · pass +6 |
| gson | 24/32 · 72%/90% | **27/32 · 80%/94%** | iR +8% · uR +4% · pass +3 |
| express | 21/32 · 64%/100% | **32/32 · 94%/100%** | iR +30% · uR +0% · pass +11 |

###### 档位 E

| 仓 | Before | After | Δ |
| --- | --- | --- | --- |
| pando | 20/22 · 91%/95% | 20/22 · 91%/95% | iR -0% · uR +0% · pass 0 |
| kb | 12/17 · 71%/88% | 12/17 · 71%/88% | iR -0% · uR +0% · pass 0 |
| go | 20/32 · 58%/78% | 22/32 · 61%/80% | iR +3% · uR +2% · pass +2 |
| django | 24/33 · 73%/95% | 24/33 · 73%/95% | iR -0% · uR -0% · pass 0 |
| hcl | 22/32 · 54%/74% | **24/32 · 60%/80%** | iR +6% · uR +6% · pass +2 |
| nng | 24/32 · 53%/70% | **25/32 · 54%/72%** | iR +1% · uR +2% · pass +1 |
| spdlog | 15/32 · 31%/69% | **19/32 · 34%/70%** | iR +3% · uR +1% · pass +4 |
| gson | 14/32 · 41%/87% | **22/32 · 64%/94%** | iR +23% · uR +7% · pass +8 |
| express | 23/32 · 70%/100% | **32/32 · 94%/100%** | iR +24% · uR +0% · pass +9 |

###### 档位 G

| 仓 | Before | After | Δ |
| --- | --- | --- | --- |
| pando | 20/22 · 89%/95% | 19/22 · 84%/91% | iR -5% · uR -4% · pass -1 |
| kb | 13/17 · 76%/100% | 14/17 · 82%/100% | iR +6% · uR +0% · pass +1 |
| go | 20/32 · 58%/78% | 21/32 · 58%/73% | iR -0% · uR -5% · pass +1 |
| django | 25/33 · 74%/94% | 25/33 · 74%/94% | iR -0% · uR -0% · pass 0 |
| hcl | 23/32 · 56%/77% | **26/32 · 66%/81%** | iR +10% · uR +4% · pass +3 |
| nng | 24/32 · 53%/72% | **24/32 · 53%/72%** | iR -0% · uR +0% · pass 0 |
| spdlog | 12/32 · 27%/66% | **18/32 · 33%/67%** | iR +6% · uR +1% · pass +6 |
| gson | 14/32 · 41%/87% | **23/32 · 66%/94%** | iR +25% · uR +7% · pass +9 |
| express | 23/32 · 70%/100% | **32/32 · 94%/100%** | iR +24% · uR +0% · pass +9 |

###### 档位 F

| 仓 | Before | After | Δ |
| --- | --- | --- | --- |
| pando | 21/22 · 93%/95% | 20/22 · 91%/91% | iR -2% · uR -4% · pass -1 |
| kb | 13/17 · 76%/94% | 13/17 · 76%/94% | iR +0% · uR +0% · pass 0 |
| go | 20/32 · 61%/88% | 23/32 · 66%/84% | iR +5% · uR -4% · pass +3 |
| django | 27/33 · 80%/97% | 22/33 · 65%/97% | iR -15% · uR -0% · pass -5 |
| hcl | 23/32 · 58%/81% | **27/32 · 69%/86%** | iR +11% · uR +5% · pass +4 |
| nng | 20/32 · 45%/61% | **24/32 · 53%/69%** | iR +8% · uR +8% · pass +4 |
| spdlog | 14/32 · 31%/62% | **18/32 · 33%/66%** | iR +2% · uR +4% · pass +4 |
| gson | 16/32 · 46%/90% | **24/32 · 67%/94%** | iR +21% · uR +4% · pass +8 |
| express | 32/32 · 97%/98% | **32/32 · 98%/98%** | iR +1% · uR +0% · pass 0 |

###### 总表（Before → After）

| 仓 | B | E | G | F |
| --- | --- | --- | --- | --- |
| pando | 19/22 · 86%/91% → 20/22 · 91%/91% | 20/22 · 91%/95% → 20/22 · 91%/95% | 20/22 · 89%/95% → 19/22 · 84%/91% | 21/22 · 93%/95% → 20/22 · 91%/91% |
| kb | 12/17 · 71%/88% → 12/17 · 71%/88% | 12/17 · 71%/88% → 12/17 · 71%/88% | 13/17 · 76%/100% → 14/17 · 82%/100% | 13/17 · 76%/94% → 13/17 · 76%/94% |
| go | 20/32 · 58%/89% → 20/32 · 58%/89% | 20/32 · 58%/78% → 22/32 · 61%/80% | 20/32 · 58%/78% → 21/32 · 58%/73% | 20/32 · 61%/88% → 23/32 · 66%/84% |
| django | 28/33 · 85%/98% → **27/33 · 82%/95%** | 24/33 · 73%/95% → 24/33 · 73%/95% | 25/33 · 74%/94% → 25/33 · 74%/94% | 27/33 · 80%/97% → 22/33 · 65%/97% |
| hcl | 21/32 · 58%/77% → **21/32 · 56%/78%** | 22/32 · 54%/74% → **24/32 · 60%/80%** | 23/32 · 56%/77% → **26/32 · 66%/81%** | 23/32 · 58%/81% → **27/32 · 69%/86%** |
| nng | 24/32 · 55%/80% → **25/32 · 56%/81%** | 24/32 · 53%/70% → **25/32 · 54%/72%** | 24/32 · 53%/72% → **24/32 · 53%/72%** | 20/32 · 45%/61% → **24/32 · 53%/69%** |
| spdlog | 18/32 · 41%/71% → **24/32 · 48%/78%** | 15/32 · 31%/69% → **19/32 · 34%/70%** | 12/32 · 27%/66% → **18/32 · 33%/67%** | 14/32 · 31%/62% → **18/32 · 33%/66%** |
| gson | 24/32 · 72%/90% → **27/32 · 80%/94%** | 14/32 · 41%/87% → **22/32 · 64%/94%** | 14/32 · 41%/87% → **23/32 · 66%/94%** | 16/32 · 46%/90% → **24/32 · 67%/94%** |
| express | 21/32 · 64%/100% → **32/32 · 94%/100%** | 23/32 · 70%/100% → **32/32 · 94%/100%** | 23/32 · 70%/100% → **32/32 · 94%/100%** | 32/32 · 97%/98% → **32/32 · 98%/98%** |

**结论**：

| 方向 | 仓 / 档 | 说明 |
| --- | --- | --- |
| 明显升 | Express、Gson | B/E/G/F 全面抬升；Express B **+11**；v2 收紧后 express/gson B 复核未回吐；**07-26 CLEAR** 后再抬（见下节） |
| 重分析抬升 | 七仓 CLEAR（+Pando/KB） | 弱档 A/C 受益最大；详见「七仓 CLEAR 重分析」 |
| 小幅升 | NNG、Go(E/F/G)、KB(B/C/D/E) | NNG 排序阶段 F **+4**；CLEAR 后再见 B **+3**；KB 默认 B **+1** |
| 持平 | 多数 E/G（非重分析仓） | 或仅 iR 微动 |
| 回退 | Django B/F；Pando B/F；KB G | Django B：基线 28→**27**；Pando B −1 / F −1；KB G −1 |

**保留本轮排序优化（含 relevance v2）**。收益最大在「融合池已召回、items 排不进」；Django 剩余债偏中文 NL/检索，不整段回退。七仓已 CLEAR 重分析并复测 A–G。

##### 七仓 CLEAR 重分析（本轮优化要点 + Before/After，2026-07-26～07-27）

**本轮改动要点**（分析端为主；检索端沿用 07-25 排序 v2，不改默认 B 开关）：

| 项 | 说明 |
| --- | --- |
| 摘要 prompt | 去掉「鉴权/会话/缓存」等业务套话示例，改为贴合源码真实职责（`code_summary.py` / `api_summary.py`） |
| CLEAR 重分析 | 对已入库仓强制清空后重建符号摘要 + embedding，使新 prompt 生效 |
| 复测范围 | HCL / spdlog / Express / Gson / NNG / Pando / KB 全档 **A–G**（排序 v2 之上） |
| 未完成 | Go（重建中止）；Django 未本轮 CLEAR |
| 脚本 / 明细 | `tests.scenarios.mid_oss.run_reanalyze_ag_queue`；`tests/output/_reanalyze_ag_queue_compare.md` |
| 单元格格式 | **pass/total · iR%/uR%**（数量优先） |

**效果结论**：

1. **多数档显著抬升**：七仓 × 七档中绝大多数 After ≥ Before；弱档 **A/C** 抬升最大（Gson A **+16**、spdlog A **+9**、Express A/C **+6**）。
2. **A–B 差距明显收窄**：表征修好后纯 Chunk（A）追赶符号档（B）；CLEAR 仓上 **B pass 仍全高于 A**，不改「默认开符号」。
3. **默认 B 仍成立**：五仓（开源）B 净 Δpass = (−2)+0+0+(+2)+(+3) = **+3**；业务仓 Pando B **−1**、KB B **+1**，两仓合计持平。相对 E：多数仓 B≥E，HCL/Pando 上 E 可更高但仍慢。
4. **rewrite 重档偶有回撤**：Gson F/G −1、NNG F −2、Express G −1、Pando F −1、KB G −1（always/weak 抖动），不改「勿默认 F/G」。

改前 = Design 总表重分析前基线（07-25 排序后 / 旧列）；改后 = 本轮 CLEAR + A–G。

| 仓 | 档 | Before | After | Δpass |
| --- | --- | --- | --- | ---: |
| hcl | A | 9/32 · 24%/59% | **13/32 · 34%/59%** | +4 |
| hcl | B ★ | 23/32 · 61%/77% | **21/32 · 56%/78%** | −2 |
| hcl | C | 16/32 · 43%/54% | **18/32 · 48%/55%** | +2 |
| hcl | D | 18/32 · 48%/73% | **19/32 · 53%/66%** | +1 |
| hcl | E | 22/32 · 56%/74% | **24/32 · 60%/80%** | +2 |
| hcl | F | 24/32 · 59%/85% | **27/32 · 69%/86%** | +3 |
| hcl | G | 23/32 · 58%/77% | **26/32 · 66%/81%** | +3 |
| spdlog | A | 7/32 · 14%/45% | **16/32 · 31%/47%** | +9 |
| spdlog | B ★ | 24/32 · 45%/76% | **24/32 · 48%/78%** | 0 |
| spdlog | C | 15/32 · 34%/52% | **19/32 · 38%/52%** | +4 |
| spdlog | D | 12/32 · 27%/50% | **15/32 · 31%/53%** | +3 |
| spdlog | E | 15/32 · 31%/69% | **19/32 · 34%/70%** | +4 |
| spdlog | F | 14/32 · 31%/62% | **18/32 · 33%/66%** | +4 |
| spdlog | G | 12/32 · 27%/66% | **18/32 · 33%/67%** | +6 |
| express | A | 23/32 · 72%/98% | **29/32 · 86%/98%** | +6 |
| express | B ★ | 32/32 · 94%/100% | **32/32 · 94%/100%** | 0 |
| express | C | 23/32 · 70%/98% | **29/32 · 84%/98%** | +6 |
| express | D | 28/32 · 84%/98% | **28/32 · 86%/98%** | 0 |
| express | E | 32/32 · 94%/100% | **32/32 · 94%/100%** | 0 |
| express | F | 32/32 · 98%/98% | **32/32 · 97%/98%** | 0 |
| express | G | 32/32 · 94%/100% | **31/32 · 91%/100%** | −1 |
| gson | A | 9/32 · 25%/90% | **25/32 · 70%/94%** | +16 |
| gson | B ★ | 27/32 · 80%/94% | **29/32 · 83%/95%** | +2 |
| gson | C | 12/32 · 34%/90% | **24/32 · 67%/94%** | +12 |
| gson | D | 14/32 · 40%/85% | **22/32 · 64%/93%** | +8 |
| gson | E | 22/32 · 64%/94% | **22/32 · 62%/91%** | 0 |
| gson | F | 24/32 · 67%/94% | **23/32 · 64%/91%** | −1 |
| gson | G | 23/32 · 66%/94% | **22/32 · 62%/91%** | −1 |
| nng | A | 20/32 · 40%/60% | **22/32 · 43%/62%** | +2 |
| nng | B ★ | 25/32 · 56%/81% | **28/32 · 57%/81%** | +3 |
| nng | C | 23/32 · 54%/66% | **24/32 · 52%/66%** | +1 |
| nng | D | 18/32 · 43%/67% | **23/32 · 49%/70%** | +5 |
| nng | E | 25/32 · 54%/72% | **25/32 · 54%/72%** | 0 |
| nng | F | 24/32 · 53%/69% | **22/32 · 51%/66%** | −2 |
| nng | G | 24/32 · 53%/72% | **24/32 · 54%/72%** | 0 |
| pando | A | 13/22 · 59%/86% | **15/22 · 68%/86%** | +2 |
| pando | B ★ | 20/22 · 91%/91% | **19/22 · 86%/93%** | −1 |
| pando | C | 16/22 · 70%/95% | **17/22 · 75%/100%** | +1 |
| pando | D | 18/22 · 80%/91% | **18/22 · 80%/95%** | 0 |
| pando | E | 20/22 · 91%/95% | **21/22 · 95%/98%** | +1 |
| pando | F | 20/22 · 91%/91% | **19/22 · 84%/86%** | −1 |
| pando | G | 19/22 · 84%/91% | **21/22 · 93%/95%** | +2 |
| kb | A | 6/17 · 35%/76% | **6/17 · 35%/76%** | 0 |
| kb | B ★ | 12/17 · 71%/88% | **13/17 · 76%/88%** | +1 |
| kb | C | 14/17 · 82%/94% | **15/17 · 88%/94%** | +1 |
| kb | D | 11/17 · 65%/82% | **13/17 · 76%/82%** | +2 |
| kb | E | 12/17 · 71%/88% | **13/17 · 76%/88%** | +1 |
| kb | F | 13/17 · 76%/94% | **13/17 · 76%/94%** | 0 |
| kb | G | 14/17 · 82%/100% | **13/17 · 76%/100%** | −1 |

**A–B pass 差（B−A）收窄**：

| 仓 | Before B−A | After B−A |
| --- | ---: | ---: |
| hcl | 14 | 8 |
| spdlog | 17 | 8 |
| express | 9 | 3 |
| gson | 18 | 4 |
| nng | 5 | 6 |
| pando | 7 | 4 |
| kb | 6 | 7 |

仓内序（重分析后）：HCL **F>G>E>B>D>C>A**；spdlog **B>C>E>G>F>A>D**；Express **F>B>E>G>A>C>D**；Gson **B>A>C>F>D>E>G**；NNG **B>E>G>C>D>F>A**；Pando **E>G>B>F>D>C>A**；KB **C>G>F>B>E>D>A**。

---



#### 测试用例场景列表（resolve / related）

用例明细以各仓 `ground_truth.py` 为准；下表为 **新 GT 规模与类型占比**（`extra.case_kind`）。


| 仓              | 总数     | sym | sym_nl | nl  | similar | hard |
| -------------- | ------ | --- | ------ | --- | ------- | ---- |
| Pando resolve  | **22** | 27% | 23%    | 27% | 18%     | 5%   |
| KB resolve     | **17** | 18% | 18%    | 35% | 18%     | 12%  |
| Go resolve     | **32** | 25% | 19%    | 31% | 16%     | 9%   |
| Django resolve | **33** | 24% | 18%    | 30% | 15%     | 12%  |
| HCL resolve    | **32** | 25% | 19%    | 31% | 16%     | 9%   |
| NNG resolve    | **32** | 25% | 19%    | 31% | 16%     | 9%   |
| spdlog resolve | **32** | 25% | 19%    | 31% | 16%     | 9%   |
| Gson resolve   | **32** | 25% | 19%    | 31% | 16%     | 9%   |
| Express resolve | **32** | 25% | 19%    | 31% | 16%     | 9%   |
| 本仓 related     | **11** | 36% | 27%    | 27% | —       | 9%   |


相对旧版主要变化：Go/Django **砍冗余纯符号**；**新增 HCL/NNG/spdlog/Gson/Express** 多语言中型仓同配比；本仓 related **补中文 NL 与 MR 经验定位**。

纯中文（query 无拉丁字母）规模约：Pando 3 / KB 7 / Go 2 / Django 7（合计 19）；中型开源仓另有多条中文 NL/hard；B vs E 专项见 §5.12。

路径默认：Pando `PANDO_AGENT_PATH`；KB `KB_SERVICE_PATH`；Go `GO_OSS_PATH`；Django `DJANGO_OSS_PATH`；HCL/NNG/spdlog/Gson/Express 见各 `session_support`（本地 `F:\开源项目\...`）。

---



#### 复现命令

```powershell
cd F:\Product_Dev\MOMA\Moma-CodeBase
$env:ENABLE_INCREMENTAL_SCAN="false"
$env:PYTHONPATH="F:\Product_Dev\MOMA\Moma-CodeBase"
$env:RESOLVE_CHANNEL_TIMEOUT_MS="0"

# Pando / KB / Go / Django …（略，见历史）

# 中型开源仓 A–G（含 Java Gson + JS Express）
poetry run python -m tests.scenarios.mid_oss.run_be_eval --only gson,express
poetry run python -m tests.scenarios.mid_oss.run_be_eval --skip-analyze --configs A,B,C,D,E,F,G

# 七仓默认 B 排序优化前后对比（skip rebuild）
poetry run python -m tests.scenarios.mid_oss.run_b_before_after

# 九仓 B/E/G/F 排序优化前后对比（skip rebuild；可 --only pando,kb,go,gson,express）
poetry run python -m tests.scenarios.mid_oss.run_befg_before_after
poetry run python -m tests.scenarios.mid_oss.run_befg_before_after --only gson,express

# 七仓 CLEAR 重分析 + A–G（逐仓；可 --skip-rebuild 已重建仓）
poetry run python -m tests.scenarios.mid_oss.run_reanalyze_ag_queue --only express
poetry run python -m tests.scenarios.mid_oss.run_reanalyze_ag_queue --only gson,nng
poetry run python -m tests.scenarios.mid_oss.run_reanalyze_ag_queue --only pando,kb
```

---



### 5.13 相关 ENV 速查

产品默认 **B**（选型逻辑与消融证据见 **§5.12「产品默认选型逻辑」**）。


| ENV                                            | 默认倾向           | 作用                                                 |
| ---------------------------------------------- | -------------- | -------------------------------------------------- |
| `CODE_ANALYSIS_LINE_CHUNK_ENABLED`             | ON             | 行块 / similar                                       |
| `CODE_ANALYSIS_SYMBOL_SUMMARY_ENABLED`         | **ON**（B）      | 符号摘要 / related 主力                                  |
| `CODE_ANALYSIS_SYMBOL_SUMMARY_LLM_BATCH_SIZE`  | 6              | 符号摘要单次打包数；1=逐条；超长折半重试                              |
| `CODE_ANALYSIS_SYMBOL_SUMMARY_LLM_CONCURRENCY` | 4              | 并行批次数（batch=1 时为并行符号数）                             |
| `CODE_ANALYSIS_NL_TO_CODE_ENABLED`             | **OFF**（B）     | NL 多视角 / lexicon；开则为 E                             |
| `CODE_ANALYSIS_NL_REWRITE_ENABLED`             | **OFF**（B）     | LLM 改写；难例可开 G                                      |
| `CODE_ANALYSIS_NL_REWRITE_MODE`                | weak           | `weak` | `always`（勿默认 always=F）                    |
| `CODE_ANALYSIS_RELATED_INCLUDE_GRAPH`          | OFF            | related 是否融 CodeGraph                              |
| `CODE_GRAPH_ENABLED` / `PROVIDER`              | ON / codegraph | 图谱                                                 |
| `RESOLVE_CHANNEL_TIMEOUT_MS`                   | 120000（0=不限）   | resolve 单通道超时；超时只丢该通道                               |
| `ENABLE_INCREMENTAL_SCAN`                      | 可配             | 后台增量扫描                                             |
| `PANDO_CLEAR` / `PANDO_AGENT_PATH`             | 评测用            | Pando 消融重建与路径                                      |
| `KB_*` / `GO_*` / `DJANGO_*` / `HCL_*` / `NNG_*` / `SPDLOG_*` / `GSON_*` / `EXPRESS_*` | 评测用 | 各仓 `CLEAR` / `SKIP_REBUILD` / `ABLATION_ONLY` / 路径 |


## 6. 评测与复现


| 套件               | 路径                                                           |
| ---------------- | ------------------------------------------------------------ |
| 准确率框架            | `tests/scenarios/framework/`                                 |
| 本仓图谱/向量          | `tests/scenarios/graph/`、`vector_similar/`、`vector_related/` |
| Pando 消融         | `tests/scenarios/pando_agent/`                               |
| KB 消融            | `tests/scenarios/knowledge_base/`                            |
| Go / Django 开源消融 | `tests/scenarios/go_oss/`、`django_oss/`、`oss_common/`        |
| 中型多语言开源          | `tests/scenarios/{hcl,nng,spdlog,gson,express}_oss/`、`mid_oss/` |
| Lib API          | `tests/scenarios/lib_api/`                                   |
| MR 经验            | `tests/scenarios/mr_experience/`                             |


九仓 resolve 配置对比与用例清单见 **§5.12**。

```powershell
$env:PYTHONPATH="F:\Product_Dev\MOMA\Moma-CodeBase"
poetry run pytest tests/scenarios/pando_agent/test_similar_accuracy.py -q -s
poetry run pytest tests/scenarios/pando_agent/test_related_hybrid_accuracy.py -q -s
# 强制清空重分析：$env:PANDO_CLEAR=1
```

---



## 7. Agent 使用建议（与准度对齐）

1. **主路径** `search resolve`，少手搓多通道。
2. **先读** `items`**，改前扫** `also_consider`：分离式对接；主列表保准（可带 snippet），次层含同目录兄弟文件防漏。
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

