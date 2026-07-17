# Agent 检索准度增强（队列 5/6/7 + 弱词）

日期：2026-07-17  
状态：已实现

## 改动摘要

1. **图谱**：`GraphResultNormalizer` 过滤噪音路径；空结果/不支持扩展名给出降级提示；callers/callees 清洗  
2. **符号摘要**：prompt 强调业务词+场景；入库 embedding 文本拼接路径/符号名（展示 summary 仍用原文）  
3. **MR 经验**：总结强制 plan/anchors/relevant_files；缺失时从 commit 文件回填；embed 文本含文件词；检索侧词面 rerank（弱词即时生效，无需立刻 re-analyze）

## 说明

- 符号/经验 **新写入** 才吃到更富 embed 文本；旧向量仅 pattern 词面 rerank 立刻受益  
- 开源 CodeGraph 内核未改，只改适配层
