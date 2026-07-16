# Lib Analysis Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** 落地 kind=lib 的公开接口抽取、LLM 摘要、向量化与 search api。

**Architecture:** 独立 `lib_analysis`；扫描/状态复用 repo_analysis 表；文件 worker 按 kind 分流；不做 CodeGraph。

**Tech Stack:** Python、现有 codeast、LLM/embedding、LanceDB/向量层、Click CLI

---

### Task 1: 模型与抽取
- Create: `app/lib_analysis/**`（schemes、extract、summary、vector、search、file_processor）
- Modify: analyze/search CLI、AnalysisService、FileAnalysisService

### Task 2: UT
- Create: `tests/unit/lib_analysis/test_public_api_extractor.py`
