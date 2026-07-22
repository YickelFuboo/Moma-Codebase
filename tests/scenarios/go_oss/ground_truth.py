"""Go 开源仓 resolve GT（Agent 向配比）。

目标分布约：纯符号 25–30% | 符号+NL 15–20% | 纯 NL 30–35% | similar 15–20% | 难例 10–15%。
范围：src 下 net / encoding / context 三包子集。
"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


GO_RESOLVE_CASES = [
    # ---- 纯符号 (~28%) ----
    PathSetCase(
        case_id="go.resolve.related.Server",
        description="纯符号：Server",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Server", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="go.resolve.related.ListenAndServe",
        description="纯符号：ListenAndServe",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "ListenAndServe", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="go.resolve.related.ServeMux",
        description="纯符号：ServeMux",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "ServeMux", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Marshal",
        description="纯符号：Marshal（JSON，易与 asn1 歧义）",
        expected_paths=[
            "src/encoding/json/encode.go",
            "src/encoding/json/v2_encode.go",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "Marshal", "expect_intent": "related", "case_kind": "sym"},
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
        extra={"query": "Unmarshal", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Context",
        description="纯符号：Context",
        expected_paths=["src/context/context.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Context", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="go.resolve.related.WithCancel",
        description="纯符号：WithCancel",
        expected_paths=["src/context/context.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "WithCancel", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="go.resolve.related.NewEncoder",
        description="纯符号：NewEncoder",
        expected_paths=[
            "src/encoding/json/stream.go",
            "src/encoding/json/v2_stream.go",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "NewEncoder", "expect_intent": "related", "case_kind": "sym"},
    ),
    # ---- 符号 + NL (~19%) ----
    PathSetCase(
        case_id="go.resolve.related.Client",
        description="符号+NL：Client HTTP 客户端",
        expected_paths=["src/net/http/client.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Client HTTP 客户端结构体在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Request",
        description="符号+NL：Request 请求对象",
        expected_paths=["src/net/http/request.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Request HTTP 请求对象定义在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="go.resolve.related.NewServeMux",
        description="符号+NL：NewServeMux 路由",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "NewServeMux 路由在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="go.resolve.related.WithTimeout",
        description="符号+NL：WithTimeout",
        expected_paths=["src/context/context.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "WithTimeout 超时上下文在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Cookie",
        description="符号+NL：Cookie",
        expected_paths=["src/net/http/cookie.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Cookie HTTP Cookie 解析在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="go.resolve.related.Transport",
        description="符号+NL：RoundTripper/Transport",
        expected_paths=["src/net/http/transport.go", "src/net/http/roundtrip.go"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "Transport HTTP 传输层 RoundTrip 在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    # ---- 纯 NL (~31%) ----
    PathSetCase(
        case_id="go.resolve.nl.cn_http_server",
        description="中文 NL：HTTP 服务端在哪",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 服务端在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_listen",
        description="中文 NL：监听端口启动服务在哪",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "监听端口启动 HTTP 服务在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_http_client",
        description="中文 NL：HTTP 客户端在哪",
        expected_paths=["src/net/http/client.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 客户端在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_router",
        description="中文 NL：HTTP 路由多路复用在哪",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 路由多路复用在哪", "expect_intent": "related", "case_kind": "nl"},
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
        extra={"query": "JSON 序列化在哪", "expect_intent": "related", "case_kind": "nl"},
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
        extra={"query": "JSON 反序列化在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_context_cancel",
        description="中文 NL：可取消上下文在哪",
        expected_paths=["src/context/context.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "可取消的 context 在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_context_timeout",
        description="中文 NL：带超时的上下文在哪",
        expected_paths=["src/context/context.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "带超时的上下文在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.en_http_timeout",
        description="英文 NL：client request timeout",
        expected_paths=["src/net/http/client.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "where is http client request timeout configured", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="go.resolve.nl.cn_cookie",
        description="中文 NL：读写 Cookie 在哪",
        expected_paths=["src/net/http/cookie.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "读写 HTTP Cookie 在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    # ---- similar (~16%) ----
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
            "case_kind": "similar",
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
            "case_kind": "similar",
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
            "case_kind": "similar",
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
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="go.resolve.similar.round_trip",
        description="代码片段：RoundTrip 弱改写",
        expected_paths=["src/net/http/client.go", "src/net/http/transport.go"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "func (c *Client) do(req *Request) (*Response, error) {\n"
                "\treturn send(req, c.transport())\n"
                "}\n"
            ),
            "expect_intent": "similar",
            "case_kind": "similar",
        },
    ),
    # ---- 难例 (~9%) ----
    PathSetCase(
        case_id="go.resolve.hard.ambiguous_handler",
        description="难例：Handler 同名多处，期望 http 服务端定义",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={"query": "Handler", "expect_intent": "related", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="go.resolve.hard.cn_json_vs_asn1",
        description="难例：短中文「序列化」易漂到 asn1，期望 json",
        expected_paths=[
            "src/encoding/json/encode.go",
            "src/encoding/json/v2_encode.go",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "把对象序列化成 JSON", "expect_intent": "related", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="go.resolve.hard.short_cn_mux",
        description="难例：短中文「路由」",
        expected_paths=["src/net/http/server.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "路由", "expect_intent": "related", "case_kind": "hard"},
    ),
]
