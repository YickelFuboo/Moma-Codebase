"""Go 开源仓 resolve GT：覆盖 net / encoding / context 三包。"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


GO_RESOLVE_CASES = [
    # ---- net/http 符号 ----
    PathSetCase(
        case_id="go.resolve.related.Server",
        description="纯符号：Server",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Server", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.ListenAndServe",
        description="纯符号：ListenAndServe",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "ListenAndServe", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Client",
        description="纯符号：Client",
        expected_paths=["src/net/http/client.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Client", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.ServeMux",
        description="纯符号：ServeMux",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "ServeMux", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Handler",
        description="纯符号：Handler",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Handler", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Request",
        description="纯符号：Request",
        expected_paths=["src/net/http/request.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Request", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Response",
        description="纯符号：Response",
        expected_paths=["src/net/http/response.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Response", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Cookie",
        description="纯符号：Cookie",
        expected_paths=["src/net/http/cookie.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Cookie", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.NewServeMux",
        description="中文+符号：NewServeMux 路由",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "NewServeMux 路由在哪", "expect_intent": "related"},
    ),
    # ---- encoding/json 符号 ----
    PathSetCase(
        case_id="go.resolve.related.Marshal",
        description="纯符号：Marshal",
        expected_paths=[
            "src/encoding/json/encode.go",
            "src/encoding/json/v2_encode.go",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "Marshal", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Unmarshal",
        description="纯符号：Unmarshal",
        expected_paths=[
            "src/encoding/json/decode.go",
            "src/encoding/json/v2_decode.go",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "Unmarshal", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.NewEncoder",
        description="中文+符号：NewEncoder JSON",
        expected_paths=[
            "src/encoding/json/stream.go",
            "src/encoding/json/v2_stream.go",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "NewEncoder JSON 流式编码在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.NewDecoder",
        description="纯符号：NewDecoder",
        expected_paths=[
            "src/encoding/json/stream.go",
            "src/encoding/json/v2_stream.go",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "NewDecoder", "expect_intent": "related"},
    ),
    # ---- context 符号 ----
    PathSetCase(
        case_id="go.resolve.related.Context",
        description="纯符号：Context",
        expected_paths=["src/context/context.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Context", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.WithCancel",
        description="纯符号：WithCancel",
        expected_paths=["src/context/context.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "WithCancel", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.WithTimeout",
        description="中文+符号：WithTimeout",
        expected_paths=["src/context/context.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "WithTimeout 超时上下文在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Background",
        description="纯符号：Background",
        expected_paths=["src/context/context.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Background", "expect_intent": "related"},
    ),
    # ---- 中文 NL ----
    PathSetCase(
        case_id="go.resolve.nl.cn_http_server",
        description="中文 NL：HTTP 服务端在哪",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 服务端在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_listen",
        description="中文 NL：监听端口启动服务在哪",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "监听端口启动 HTTP 服务在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_http_client",
        description="中文 NL：HTTP 客户端在哪",
        expected_paths=["src/net/http/client.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 客户端在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_router",
        description="中文 NL：HTTP 路由多路复用在哪",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 路由多路复用在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_json_marshal",
        description="中文 NL：JSON 序列化在哪",
        expected_paths=[
            "src/encoding/json/encode.go",
            "src/encoding/json/v2_encode.go",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "JSON 序列化 Marshal 在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_json_unmarshal",
        description="中文 NL：JSON 反序列化在哪",
        expected_paths=[
            "src/encoding/json/decode.go",
            "src/encoding/json/v2_decode.go",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "JSON 反序列化 Unmarshal 在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_context_cancel",
        description="中文 NL：可取消上下文在哪",
        expected_paths=["src/context/context.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "可取消的 context 在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_context_timeout",
        description="中文 NL：带超时的上下文在哪",
        expected_paths=["src/context/context.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "带超时的上下文在哪", "expect_intent": "related"},
    ),
    # ---- similar ----
    PathSetCase(
        case_id="go.resolve.similar.listen_and_serve",
        description="代码片段：ListenAndServe",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "func ListenAndServe(addr string, handler Handler) error {\n"
                "\tserver := &Server{Addr: addr, Handler: handler}\n"
                "\treturn server.ListenAndServe()\n"
                "}\n"
            ),
            "expect_intent": "similar",
        },
    ),
    PathSetCase(
        case_id="go.resolve.similar.client_struct",
        description="代码片段：type Client struct",
        expected_paths=["src/net/http/client.go"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "type Client struct {\n"
                "\tTransport RoundTripper\n"
                "\tCheckRedirect func(req *Request, via []*Request) error\n"
                "\tJar CookieJar\n"
                "\tTimeout time.Duration\n"
                "}\n"
            ),
            "expect_intent": "similar",
        },
    ),
    PathSetCase(
        case_id="go.resolve.similar.marshal",
        description="代码片段：Marshal",
        expected_paths=[
            "src/encoding/json/encode.go",
            "src/encoding/json/v2_encode.go",
        ],
        min_precision=0.3,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "func Marshal(v any) ([]byte, error) {\n"
                "\tif v == nil {\n"
                "\t\treturn []byte(\"null\"), nil\n"
                "\t}\n"
                "\te := newEncodeState()\n"
            ),
            "expect_intent": "similar",
        },
    ),
    PathSetCase(
        case_id="go.resolve.similar.with_cancel",
        description="代码片段：WithCancel",
        expected_paths=["src/context/context.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "func WithCancel(parent Context) (ctx Context, cancel CancelFunc) {\n"
                "\tc := newCancelCtx(parent)\n"
                "\tpropagateCancel(parent, &c)\n"
                "\treturn &c, func() { c.cancel(true, Canceled, nil) }\n"
                "}\n"
            ),
            "expect_intent": "similar",
        },
    ),
]
