# Pando-CodeBase-Plugin

本地代码仓分析 CLI 工具。

## 安装

```bash
poetry install
```

## 配置

复制 `env.example` 为 `env`，按需修改数据库、向量库、Neo4j、模型配置等。

模型清单：`{RUNTIME_DATA_DIR}/models/chat_models.json`、`embedding_models.json`

## 使用

```bash
# 数据库迁移
poetry run pcb migrate

# 登记代码仓（名称默认取目录名）
poetry run pcb repo add --path F:\myproject

# 列出 / 查看 / 删除
poetry run pcb repo list
poetry run pcb repo show --path F:\myproject
poetry run pcb repo delete --path F:\myproject

# 启动全仓分析
poetry run pcb analyze start --path F:\myproject
poetry run pcb analyze status --path F:\myproject

# 前台运行文件分析调度器（另开终端）
poetry run pcb worker

# 代码检索
poetry run pcb search similar --path F:\myproject --code "def foo():"
poetry run pcb search related --path F:\myproject --keywords "auth,login"
```

安装后可直接使用 `pcb` 命令（Poetry scripts）。
