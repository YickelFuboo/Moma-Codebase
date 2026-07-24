"""nanomsg/nng resolve GT（Agent 向配比）。

目标：纯符号 25–30% | 符号+NL 15–20% | 纯 NL 30–35% | similar 15–20% | 难例 10–15%。
本文件 32 条：sym8 / sym_nl6 / nl10 / similar5 / hard3。
"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


NNG_RESOLVE_CASES = [
    # ---- 纯符号 (~25%) ----
    PathSetCase(
        case_id="nng.resolve.related.nng_socket",
        description="纯符号：nng_socket",
        expected_paths=["include/nng/nng.h", "src/core/socket.c", "src/core/socket.h"],
        min_precision=0.15,
        min_recall=0.33,
        top_k=5,
        extra={"query": "nng_socket", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_aio",
        description="纯符号：nng_aio",
        expected_paths=["include/nng/nng.h", "src/core/aio.c", "src/core/aio.h"],
        min_precision=0.15,
        min_recall=0.33,
        top_k=5,
        extra={"query": "nng_aio", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_dialer",
        description="纯符号：nng_dialer",
        expected_paths=["src/core/dialer.c", "src/core/dialer.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nng_dialer", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_listener",
        description="纯符号：nng_listener",
        expected_paths=["src/core/listener.c", "src/core/listener.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nng_listener", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_msg",
        description="纯符号：nng_msg / message",
        expected_paths=["src/core/message.c", "src/core/message.h", "include/nng/nng.h"],
        min_precision=0.15,
        min_recall=0.33,
        top_k=5,
        extra={"query": "nng_msg", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nni_pipe",
        description="纯符号：pipe",
        expected_paths=["src/core/pipe.c", "src/core/pipe.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nni_pipe", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_ctx",
        description="纯符号：nng_ctx",
        expected_paths=["src/core/socket.c", "include/nng/nng.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nng_ctx", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.msgqueue",
        description="纯符号：msgqueue",
        expected_paths=["src/core/msgqueue.c", "src/core/msgqueue.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nni_msgq", "case_kind": "sym"},
    ),
    # ---- 符号+NL (~19%) ----
    PathSetCase(
        case_id="nng.resolve.related.http_server",
        description="符号+NL：HTTP server",
        expected_paths=["src/supplemental/http/http_server.c", "include/nng/http.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "http_server HTTP 服务端在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.http_client",
        description="符号+NL：HTTP client",
        expected_paths=["src/supplemental/http/http_client.c", "include/nng/http.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "http_client HTTP 客户端在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_aio_nl",
        description="符号+NL：aio 异步完成",
        expected_paths=["src/core/aio.c", "src/core/aio.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nng_aio 异步完成回调在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_dialer_nl",
        description="符号+NL：dialer 主动连接",
        expected_paths=["src/core/dialer.c", "src/core/dialer.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nng_dialer 主动拨号连接在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.nng_listener_nl",
        description="符号+NL：listener 监听",
        expected_paths=["src/core/listener.c", "src/core/listener.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nng_listener 监听接受连接在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.related.socket_nl",
        description="符号+NL：socket 套接字",
        expected_paths=["src/core/socket.c", "include/nng/nng.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "nng_socket 套接字实现在哪", "case_kind": "sym_nl"},
    ),
    # ---- 纯 NL (~31%) ----
    PathSetCase(
        case_id="nng.resolve.nl.cn_socket",
        description="中文 NL：套接字实现在哪",
        expected_paths=["src/core/socket.c", "include/nng/nng.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "套接字 socket 实现在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_async_io",
        description="中文 NL：异步 IO 在哪",
        expected_paths=["src/core/aio.c", "src/core/aio.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "异步 IO aio 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_dial",
        description="中文 NL：主动连接 dialer 在哪",
        expected_paths=["src/core/dialer.c"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "主动连接 dialer 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_http_server",
        description="中文 NL：HTTP 服务端在哪",
        expected_paths=["src/supplemental/http/http_server.c"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 服务端实现在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_listen",
        description="中文 NL：监听端口在哪",
        expected_paths=["src/core/listener.c", "src/core/listener.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "监听端口接受连接在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_message",
        description="中文 NL：消息对象在哪",
        expected_paths=["src/core/message.c", "src/core/message.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "消息对象 message 实现在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_http_client",
        description="中文 NL：HTTP 客户端在哪",
        expected_paths=["src/supplemental/http/http_client.c"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 客户端实现在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_msgqueue",
        description="中文 NL：消息队列在哪",
        expected_paths=["src/core/msgqueue.c", "src/core/msgqueue.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "消息队列实现在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.en_async_io",
        description="英文 NL：async IO completion",
        expected_paths=["src/core/aio.c", "src/core/aio.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "where is async IO completion implemented", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="nng.resolve.nl.cn_pipe",
        description="中文 NL：管道 pipe 在哪",
        expected_paths=["src/core/pipe.c", "src/core/pipe.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "连接管道 pipe 实现在哪", "case_kind": "nl"},
    ),
    # ---- similar (~16%) ----
    PathSetCase(
        case_id="nng.resolve.similar.socket_close",
        description="代码片段：socket close 风格",
        expected_paths=["src/core/socket.c"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "int\n"
                "nng_socket_close(nng_socket s)\n"
                "{\n"
                "\tnni_sock *sock;\n"
                "\tint       rv;\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="nng.resolve.similar.aio_finish",
        description="代码片段：aio finish 风格",
        expected_paths=["src/core/aio.c"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "void\n"
                "nni_aio_finish(nni_aio *aio, int rv, size_t count)\n"
                "{\n"
                "\tnni_aio_finish_impl(aio, rv, count, NULL, false);\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="nng.resolve.similar.dialer_start",
        description="代码片段：dialer start",
        expected_paths=["src/core/dialer.c"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "int\n"
                "nni_dialer_start(nni_dialer *d, int flags)\n"
                "{\n"
                "\tint rv;\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="nng.resolve.similar.http_server",
        description="代码片段：http server handler",
        expected_paths=["src/supplemental/http/http_server.c"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "static void\n"
                "http_handler(void *arg)\n"
                "{\n"
                "\tnng_http_handler *h = arg;\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="nng.resolve.similar.message_alloc",
        description="代码片段：message alloc",
        expected_paths=["src/core/message.c"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "int\n"
                "nni_msg_alloc(nni_msg **mp, size_t size)\n"
                "{\n"
                "\tnni_msg *m;\n"
            ),
            "case_kind": "similar",
        },
    ),
    # ---- 难例 (~9%) ----
    PathSetCase(
        case_id="nng.resolve.hard.cn_message",
        description="难例：短中文「消息收发」",
        expected_paths=["src/core/message.c", "src/core/msgqueue.c"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "消息收发", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="nng.resolve.hard.cn_connect",
        description="难例：短中文「连接」",
        expected_paths=["src/core/dialer.c", "src/core/listener.c", "src/core/pipe.c"],
        min_precision=0.1,
        min_recall=0.33,
        top_k=10,
        extra={"query": "建立连接", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="nng.resolve.hard.close_ambiguous",
        description="难例：close 多处同名",
        expected_paths=["src/core/socket.c", "src/core/dialer.c", "src/core/listener.c"],
        min_precision=0.1,
        min_recall=0.33,
        top_k=8,
        extra={"query": "close", "case_kind": "hard"},
    ),
]
