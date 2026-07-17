# Inspect 只读验收 CLI 设计

日期：2026-07-17  
状态：已批准

## 边界

- CLI + JSON；可选 `--export`
- `--target` / `--file` 可选：不填 = 全仓/全库；填了 = 子目录前缀或单文件
- 默认 `--limit 500`；`0` 表示不限制
- kind：chunks/graph → code；apis → lib

## 命令

```text
mcb inspect chunks --path ... [--target ...] [--limit 500] [--full-content] [--export f.json]
mcb inspect graph  --path ... [--target ...] [--limit 500] [--export f.json]
mcb inspect apis   --path ... [--file ...] [--limit 500] [--export f.json]
```
