# MR Experience Implementation Plan

**Goal:** 本地 git 历史沉淀开发经验，支持 experience CLI 与 search pattern。

**Architecture:** mr_experience 独立管线；规则筛文件 + LLM；failed 不进向量，可重试。

---

### Tasks
1. DB 模型 + alembic
2. git/filter/summarizer/vector/service
3. CLI + search pattern
4. UT + 场景
