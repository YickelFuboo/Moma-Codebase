"""gabime/spdlog resolve GT（Agent 向配比）。

目标：纯符号 25–30% | 符号+NL 15–20% | 纯 NL 30–35% | similar 15–20% | 难例 10–15%。
本文件 32 条：sym8 / sym_nl6 / nl10 / similar5 / hard3。
"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


SPDLOG_RESOLVE_CASES = [
    # ---- 纯符号 (~25%) ----
    PathSetCase(
        case_id="spdlog.resolve.related.logger",
        description="纯符号：logger",
        expected_paths=["include/spdlog/logger.h", "include/spdlog/logger-inl.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "logger", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.set_level",
        description="纯符号：set_level",
        expected_paths=["include/spdlog/spdlog.h", "include/spdlog/logger.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "set_level", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.async_logger",
        description="纯符号：async_logger",
        expected_paths=["include/spdlog/async_logger.h", "include/spdlog/async.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "async_logger", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.rotating_file_sink",
        description="纯符号：rotating_file_sink",
        expected_paths=[
            "include/spdlog/sinks/rotating_file_sink.h",
            "include/spdlog/sinks/rotating_file_sink-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "rotating_file_sink", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.basic_file_sink",
        description="纯符号：basic_file_sink",
        expected_paths=[
            "include/spdlog/sinks/basic_file_sink.h",
            "include/spdlog/sinks/basic_file_sink-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "basic_file_sink", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.registry",
        description="纯符号：registry",
        expected_paths=[
            "include/spdlog/details/registry.h",
            "include/spdlog/details/registry-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "registry", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.thread_pool",
        description="纯符号：thread_pool",
        expected_paths=[
            "include/spdlog/details/thread_pool.h",
            "include/spdlog/details/thread_pool-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "thread_pool", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.daily_file_sink",
        description="纯符号：daily_file_sink",
        expected_paths=["include/spdlog/sinks/daily_file_sink.h"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "daily_file_sink", "case_kind": "sym"},
    ),
    # ---- 符号+NL (~19%) ----
    PathSetCase(
        case_id="spdlog.resolve.related.pattern_formatter",
        description="符号+NL：pattern_formatter",
        expected_paths=[
            "include/spdlog/pattern_formatter.h",
            "include/spdlog/pattern_formatter-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "pattern_formatter 日志格式化在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.basic_file_sink_nl",
        description="符号+NL：basic_file_sink",
        expected_paths=[
            "include/spdlog/sinks/basic_file_sink.h",
            "include/spdlog/sinks/basic_file_sink-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=5,
        extra={"query": "basic_file_sink 写文件 sink 在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.async_logger_nl",
        description="符号+NL：async_logger",
        expected_paths=["include/spdlog/async_logger.h", "include/spdlog/async.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "async_logger 异步日志器在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.rotating_nl",
        description="符号+NL：rotating_file_sink",
        expected_paths=["include/spdlog/sinks/rotating_file_sink.h"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "rotating_file_sink 滚动文件在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.set_level_nl",
        description="符号+NL：set_level",
        expected_paths=["include/spdlog/spdlog.h", "include/spdlog/logger.h"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "set_level 设置日志级别在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.related.stdout_color_nl",
        description="符号+NL：stdout_color_sinks",
        expected_paths=[
            "include/spdlog/sinks/stdout_color_sinks.h",
            "include/spdlog/sinks/ansicolor_sink.h",
        ],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "stdout_color_sinks 彩色控制台输出在哪", "case_kind": "sym_nl"},
    ),
    # ---- 纯 NL (~31%) ----
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_logger",
        description="中文 NL：日志器定义在哪",
        expected_paths=["include/spdlog/logger.h", "include/spdlog/spdlog.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "日志器 logger 定义在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_set_level",
        description="中文 NL：设置日志级别在哪",
        expected_paths=["include/spdlog/spdlog.h", "include/spdlog/logger.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "设置日志级别在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_rotate_file",
        description="中文 NL：滚动文件日志在哪",
        expected_paths=["include/spdlog/sinks/rotating_file_sink.h"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "滚动文件日志 sink 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_async",
        description="中文 NL：异步日志在哪",
        expected_paths=["include/spdlog/async.h", "include/spdlog/async_logger.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "异步日志在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_pattern",
        description="中文 NL：日志格式化在哪",
        expected_paths=[
            "include/spdlog/pattern_formatter.h",
            "include/spdlog/pattern_formatter-inl.h",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "日志格式化 pattern 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_basic_file",
        description="中文 NL：写文件 sink 在哪",
        expected_paths=["include/spdlog/sinks/basic_file_sink.h"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "写文件日志 sink 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_registry",
        description="中文 NL：日志器注册表在哪",
        expected_paths=["include/spdlog/details/registry.h"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "日志器注册表 registry 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_daily",
        description="中文 NL：按天滚动文件在哪",
        expected_paths=["include/spdlog/sinks/daily_file_sink.h"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "按天滚动文件日志在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.en_async",
        description="英文 NL：async logging",
        expected_paths=["include/spdlog/async.h", "include/spdlog/async_logger.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "where is async logging implemented", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.nl.cn_console",
        description="中文 NL：控制台彩色输出在哪",
        expected_paths=[
            "include/spdlog/sinks/stdout_color_sinks.h",
            "include/spdlog/sinks/ansicolor_sink.h",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "控制台彩色日志输出在哪", "case_kind": "nl"},
    ),
    # ---- similar (~16%) ----
    PathSetCase(
        case_id="spdlog.resolve.similar.logger_info",
        description="代码片段：logger info 风格",
        expected_paths=["include/spdlog/logger.h", "include/spdlog/spdlog.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "template <typename... Args>\n"
                "void info(format_string_t<Args...> fmt, Args &&...args) {\n"
                "    log(level::info, fmt, std::forward<Args>(args)...);\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="spdlog.resolve.similar.set_level",
        description="代码片段：set_level",
        expected_paths=["include/spdlog/logger.h", "include/spdlog/spdlog.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "void set_level(level::level_enum log_level);\n"
                "level::level_enum level() const;\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="spdlog.resolve.similar.rotating_sink",
        description="代码片段：rotating sink rotate",
        expected_paths=[
            "include/spdlog/sinks/rotating_file_sink.h",
            "include/spdlog/sinks/rotating_file_sink-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "void rotate_() {\n"
                "    using details::os::filename_to_str;\n"
                "    rename_file_(filename(), calc_filename(base_filename_, 1));\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="spdlog.resolve.similar.async_logger",
        description="代码片段：async_logger sink_it",
        expected_paths=["include/spdlog/async_logger.h", "include/spdlog/async_logger-inl.h"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "void sink_it_(const details::log_msg &msg) override {\n"
                "    if (auto pool_ptr = thread_pool_.lock()) {\n"
                "        pool_ptr->post_log(shared_from_this(), msg, overflow_policy_);\n"
                "    }\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="spdlog.resolve.similar.pattern_fmt",
        description="代码片段：pattern formatter",
        expected_paths=[
            "include/spdlog/pattern_formatter.h",
            "include/spdlog/pattern_formatter-inl.h",
        ],
        min_precision=0.2,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "void format(const details::log_msg &msg, memory_buf_t &dest) override;\n"
                "void set_pattern(const std::string &pattern);\n"
            ),
            "case_kind": "similar",
        },
    ),
    # ---- 难例 (~9%) ----
    PathSetCase(
        case_id="spdlog.resolve.hard.cn_sink",
        description="难例：短中文「输出到文件」",
        expected_paths=[
            "include/spdlog/sinks/basic_file_sink.h",
            "include/spdlog/sinks/rotating_file_sink.h",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "输出到文件", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.hard.cn_level",
        description="难例：短中文「日志级别」",
        expected_paths=["include/spdlog/spdlog.h", "include/spdlog/logger.h"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "日志级别", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="spdlog.resolve.hard.sink_ambiguous",
        description="难例：sink 多实现",
        expected_paths=[
            "include/spdlog/sinks/sink.h",
            "include/spdlog/sinks/base_sink.h",
            "include/spdlog/sinks/basic_file_sink.h",
        ],
        min_precision=0.1,
        min_recall=0.33,
        top_k=8,
        extra={"query": "sink", "case_kind": "hard"},
    ),
]
