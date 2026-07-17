# search resolve 场景化增强

日期：2026-07-17  
状态：已实现（UT 23 passed；Pando resolve 3/3 intent+Top1 均 OK）

## 目标

1. 中文 query 能抽出可用 related 关键词（不只英文标识符）
2. pattern 结果若含 relevant_files/anchors，展开为可与 related 对齐的 file 项再融合
3. Pando 真仓场景：`resolve` 对符号定位 / 代码片段 的 intent + Top1 可用

## 非目标

完整中文 NLP 分词引擎；远程 MR API
