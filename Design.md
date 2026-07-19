# MomaCodeBase Design

日期：2026-07-18  
状态：能力已落地；本文为总设计（已并入原 `docs/superpowers/specs/` 中相关方案）

本文说明：支持的分析/检索场景、各环节**具体技术方案**、准确率关键手段，以及优化前后评测对比。CLI 与 Agent 对接见 [README.md](README.md)。

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

---

## 5. 优化前后对比数据

口径：

- **P** = Precision，**R** = Recall（相对 GT 文件或标题集合）  
- **Top1** = 第一条是否命中期望定义文件  
- 真仓默认 **Pando-Agent**（`PANDO_AGENT_PATH`）；本仓场景覆盖图谱 + 向量子集  

### 5.1 similar（Pando）

| 阶段 | 用例 | avg P | avg R | Top1 | 列表形态 |
|------|------|-------|-------|------|----------|
| 优化前（仅宽召回） | 6 近原文 | ~22% | 100% | 未单列（存在首位漂移） | 常填满 top_k≈10 |
| 多视角 + rerank | 6 近原文 | ~17.5%* | 100% | **6/6** | 更短（如 3～4） |
| + 短列表截断（0.82 门槛/配额/软上限） | 6 近原文 | **100%** | **100%** | **6/6** | 多数 **n=1** |
| 弱改写（未做稀有/路径加权） | 4 弱案 | ~62% | 100% | ~2/4 | n≈1.75 |
| + 稀有 token / 路径加权 | 4 弱案 | **~88%** | **100%** | **4/4** | 短列表 |

\*截断后分母变小会导致平均 P 数字一度下降；对 Agent 关键的是 **Top1 + 短列表**，故继续收敛到 n≈1。

本仓 `tests/scenarios/vector_similar/`：**8/8** 通过。

### 5.2 related 通道消融（Pando 同 GT）

| 组合 | avg P | avg R | 解读 |
|------|-------|-------|------|
| symbol only | ~81% | 100% | 精确定位主力 |
| chunk only | ~19% | ~90% | 找定义噪声大 |
| codegraph only | ~10% | ~10% | 返回调用方，不适合作定义检索 |
| symbol + chunk | ~81% | 100% | ≈ 仅 symbol |
| chunk + codegraph | ~12% | ~90% | 无 exact 时崩 |
| **symbol + codegraph** | **~92%** | **100%** | 最佳两两组合 |

全仓 `app/` 早期宽检索：avg **P≈12% / R=100%**。  
收紧 exact + 融合截断后，精确定位 Precision 显著抬升（核心子集曾 **P≈77% / R=100%**；消融最佳 **92%**）。

同 GT 参考：Cursor/Codegraph 风格短列表约 **P≈42% / R=100%**——差距在「返回条数与定义优先」，而非漏召回。

### 5.3 resolve（Pando）

| 阶段 | 结果 |
|------|------|
| pattern 通道 bug | `intent=pattern` 失败，只剩 related |
| 修复 + 中文关键词 + 文件展开 | UT 通过；场景 resolve **3/3** intent+Top1 OK |

### 5.4 pattern / MR 经验（Pando）

| 阶段 | ready / skipped | 向量条数 | 检索观感 |
|------|-----------------|----------|----------|
| 旧 changelog | 13 / 0 | ≈13 | 偏 diff 复述 |
| 预筛 + extractable | 10 / 3 | ≈10 | 无价值 MR 被 skip |
| 单 MR 多经验 | 10 / 3 | ≈29 | 更细，但混运维型 |
| 质量/changelog 过滤 | 10 / 3 | **≈23** | Top 偏架构决策 |

### 5.5 本仓综合场景

| 指标 | 数值 |
|------|------|
| 用例 | 29（图谱 15 + related 6 + similar 8） |
| 通过 | **29/29** |
| avg P / R | **~58% / ~98%** |

---

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
