# CLI JSON 输出结构（search 查询类）

机器调用通过一次性 CLI。stdout **仅输出 JSON**。实现见 `app/cli/schemes.py`（`ExitCode` / `ErrorCode` / `ResponseScheme`）。

适用范围：`search resolve` 及全部单能力查询（`similar` / `related` / `chunks` / `symbols` / `api` / `pattern` / `dependents` / `dependencies` / `callers` / `callees`）。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功（`ok: true`） |
| 1 | 用法错误（Click 参数缺失等） |
| 2 | 业务错误（未登记仓、能力关闭等，`ok: false`） |
| 3 | 超时（`--timeout-ms` > 0 且超时） |
| 4 | 系统错误 |

查询类命令均支持 `--timeout-ms`（默认 0=不限制）。超时示例：

```json
{
  "ok": false,
  "error": {
    "code": "timeout",
    "message": "操作超时（3000 ms）",
    "details": {"timeout_ms": 3000}
  }
}
```

## 成功信封

通用 search（单能力）：必填 `ok`、`total`、`items`。

`resolve` 额外：必填 `query`；每条 item 至少含 `file_path` / `symbol_name` / `title` / `api_name` 之一。默认可带 `snippet`（`--with-content`）。

图谱类会同时保留原字段（如 `dependents` / `dependencies`），并归一到 `items`。

## 失败信封

```json
{
  "ok": false,
  "error": {
    "code": "repo_not_found",
    "message": "仓库未登记: F:/x"
  }
}
```

稳定 `error.code`：`repo_not_found` | `permission_denied` | `business_error` | `timeout` | `system_error`。
