"""expressjs/express resolve GT（Agent 向配比）。

目标：纯符号 25–30% | 符号+NL 15–20% | 纯 NL 30–35% | similar 15–20% | 难例 10–15%。
本文件 32 条：sym8 / sym_nl6 / nl10 / similar5 / hard3。
"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


EXPRESS_RESOLVE_CASES = [
    # ---- 纯符号 (~25%) ----
    PathSetCase(
        case_id="express.resolve.related.createApplication",
        description="纯符号：createApplication",
        expected_paths=["lib/express.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "createApplication", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="express.resolve.related.app_use",
        description="纯符号：app.use",
        expected_paths=["lib/application.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "app.use", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="express.resolve.related.app_listen",
        description="纯符号：app.listen",
        expected_paths=["lib/application.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "listen", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="express.resolve.related.app_handle",
        description="纯符号：app.handle",
        expected_paths=["lib/application.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "handle", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="express.resolve.related.res_json",
        description="纯符号：res.json",
        expected_paths=["lib/response.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "res.json", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="express.resolve.related.res_send",
        description="纯符号：res.send",
        expected_paths=["lib/response.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "res.send", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="express.resolve.related.res_render",
        description="纯符号：res.render",
        expected_paths=["lib/response.js", "lib/view.js"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "res.render", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="express.resolve.related.req_get",
        description="纯符号：req.get",
        expected_paths=["lib/request.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "req.get", "case_kind": "sym"},
    ),
    # ---- 符号+NL (~19%) ----
    PathSetCase(
        case_id="express.resolve.related.app_use_nl",
        description="符号+NL：中间件注册 use",
        expected_paths=["lib/application.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "app.use 注册中间件在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="express.resolve.related.app_listen_nl",
        description="符号+NL：listen 启动服务",
        expected_paths=["lib/application.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "app.listen 启动 HTTP 服务在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="express.resolve.related.res_json_nl",
        description="符号+NL：res.json 返回 JSON",
        expected_paths=["lib/response.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "res.json 返回 JSON 响应在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="express.resolve.related.res_send_nl",
        description="符号+NL：res.send 发送响应",
        expected_paths=["lib/response.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "res.send 发送响应体在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="express.resolve.related.app_route_nl",
        description="符号+NL：app.route 路由",
        expected_paths=["lib/application.js"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "app.route 定义路由在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="express.resolve.related.res_render_nl",
        description="符号+NL：res.render 渲染视图",
        expected_paths=["lib/response.js", "lib/view.js"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "res.render 渲染视图模板在哪", "case_kind": "sym_nl"},
    ),
    # ---- 纯 NL (~31%) ----
    PathSetCase(
        case_id="express.resolve.nl.cn_middleware",
        description="中文 NL：注册中间件在哪",
        expected_paths=["lib/application.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "注册中间件在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_listen",
        description="中文 NL：启动 HTTP 服务在哪",
        expected_paths=["lib/application.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "启动 HTTP 监听服务在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_json_response",
        description="中文 NL：返回 JSON 响应在哪",
        expected_paths=["lib/response.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "返回 JSON 响应在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_send_body",
        description="中文 NL：发送响应体在哪",
        expected_paths=["lib/response.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "发送响应体在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_create_app",
        description="中文 NL：创建应用实例在哪",
        expected_paths=["lib/express.js", "index.js"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "创建 express 应用实例在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_route",
        description="中文 NL：定义路由在哪",
        expected_paths=["lib/application.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "定义路由在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_render_view",
        description="中文 NL：渲染视图在哪",
        expected_paths=["lib/response.js", "lib/view.js"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "渲染视图模板在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_request_header",
        description="中文 NL：读取请求头在哪",
        expected_paths=["lib/request.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "读取请求头在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.en_middleware",
        description="英文 NL：register middleware",
        expected_paths=["lib/application.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "where to register middleware", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="express.resolve.nl.cn_handle_request",
        description="中文 NL：处理请求入口在哪",
        expected_paths=["lib/application.js", "lib/express.js"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "处理请求入口在哪", "case_kind": "nl"},
    ),
    # ---- similar (~16%) ----
    PathSetCase(
        case_id="express.resolve.similar.app_use",
        description="代码片段：app.use",
        expected_paths=["lib/application.js"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "app.use = function use(fn) {\n"
                "  var offset = 0;\n"
                "  var path = '/';\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="express.resolve.similar.app_listen",
        description="代码片段：app.listen",
        expected_paths=["lib/application.js"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "app.listen = function listen() {\n"
                "  var server = http.createServer(this);\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="express.resolve.similar.res_json",
        description="代码片段：res.json",
        expected_paths=["lib/response.js"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "res.json = function json(obj) {\n"
                "  var val = obj;\n"
                "  // allow status / body\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="express.resolve.similar.create_app",
        description="代码片段：createApplication",
        expected_paths=["lib/express.js"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "function createApplication() {\n"
                "  var app = function(req, res, next) {\n"
                "    app.handle(req, res, next);\n"
                "  };\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="express.resolve.similar.res_send",
        description="代码片段：res.send",
        expected_paths=["lib/response.js"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "res.send = function send(body) {\n"
                "  var chunk = body;\n"
                "  var encoding;\n"
            ),
            "case_kind": "similar",
        },
    ),
    # ---- 难例 (~9%) ----
    PathSetCase(
        case_id="express.resolve.hard.cn_route",
        description="难例：短中文「路由」",
        expected_paths=["lib/application.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "路由", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="express.resolve.hard.send_ambiguous",
        description="难例：send 多义",
        expected_paths=["lib/response.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=8,
        extra={"query": "send", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="express.resolve.hard.cn_response",
        description="难例：短中文「返回响应」",
        expected_paths=["lib/response.js"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "返回响应", "case_kind": "hard"},
    ),
]
