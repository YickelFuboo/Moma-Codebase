"""search resolve 统一检索编排设计。

日期：2026-07-17
状态：已实现

## 目标

Agent 一次调用 `search resolve --path --query [--intent]`，由规则路由自动组合 similar/related/pattern/api/graph。

## Intent

| 值 | 别名 | 通道 |
|----|------|------|
| auto | （默认） | 规则检测 |
| similar | | similar |
| related | locate | related |
| pattern | experience | pattern + related |
| api | | api（仅 lib） |
| graph | | dependents/callers 等；抽不出目标则降级 related |

## 输出

intent / channels_used / items（融合） / sections（分通道） / channel_errors（可选）
"""
