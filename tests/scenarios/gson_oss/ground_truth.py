"""google/gson resolve GT（Agent 向配比）。

目标：纯符号 25–30% | 符号+NL 15–20% | 纯 NL 30–35% | similar 15–20% | 难例 10–15%。
本文件 32 条：sym8 / sym_nl6 / nl10 / similar5 / hard3。
"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


_GSON = "gson/src/main/java/com/google/gson"

GSON_RESOLVE_CASES = [
    # ---- 纯符号 (~25%) ----
    PathSetCase(
        case_id="gson.resolve.related.Gson",
        description="纯符号：Gson",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Gson", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.fromJson",
        description="纯符号：fromJson",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "fromJson", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.toJson",
        description="纯符号：toJson",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "toJson", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.GsonBuilder",
        description="纯符号：GsonBuilder",
        expected_paths=[f"{_GSON}/GsonBuilder.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "GsonBuilder", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.JsonParser",
        description="纯符号：JsonParser",
        expected_paths=[f"{_GSON}/JsonParser.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "JsonParser", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.TypeAdapter",
        description="纯符号：TypeAdapter",
        expected_paths=[f"{_GSON}/TypeAdapter.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "TypeAdapter", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.TypeToken",
        description="纯符号：TypeToken",
        expected_paths=[f"{_GSON}/reflect/TypeToken.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "TypeToken", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.JsonReader",
        description="纯符号：JsonReader",
        expected_paths=[f"{_GSON}/stream/JsonReader.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "JsonReader", "case_kind": "sym"},
    ),
    # ---- 符号+NL (~19%) ----
    PathSetCase(
        case_id="gson.resolve.related.fromJson_nl",
        description="符号+NL：fromJson 反序列化",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "fromJson JSON 反序列化在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.toJson_nl",
        description="符号+NL：toJson 序列化",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "toJson 对象序列化成 JSON 在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.GsonBuilder_nl",
        description="符号+NL：GsonBuilder 配置",
        expected_paths=[f"{_GSON}/GsonBuilder.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "GsonBuilder 构建配置 Gson 在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.JsonParser_nl",
        description="符号+NL：JsonParser 解析",
        expected_paths=[f"{_GSON}/JsonParser.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "JsonParser 解析 JSON 树在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.TypeAdapter_nl",
        description="符号+NL：TypeAdapter 自定义适配",
        expected_paths=[f"{_GSON}/TypeAdapter.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "TypeAdapter 自定义类型适配在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.related.JsonWriter_nl",
        description="符号+NL：JsonWriter 写出",
        expected_paths=[f"{_GSON}/stream/JsonWriter.java"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "JsonWriter 流式写出 JSON 在哪", "case_kind": "sym_nl"},
    ),
    # ---- 纯 NL (~31%) ----
    PathSetCase(
        case_id="gson.resolve.nl.cn_from_json",
        description="中文 NL：JSON 反序列化在哪",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "JSON 反序列化成对象在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_to_json",
        description="中文 NL：对象转 JSON 在哪",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "对象序列化成 JSON 字符串在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_builder",
        description="中文 NL：配置 Gson 构建器在哪",
        expected_paths=[f"{_GSON}/GsonBuilder.java"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "配置 Gson 构建器在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_parse_tree",
        description="中文 NL：解析 JSON 树在哪",
        expected_paths=[f"{_GSON}/JsonParser.java", f"{_GSON}/JsonElement.java"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "解析 JSON 成树结构在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_type_token",
        description="中文 NL：泛型类型令牌在哪",
        expected_paths=[f"{_GSON}/reflect/TypeToken.java"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "泛型 TypeToken 类型令牌在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_stream_reader",
        description="中文 NL：流式读 JSON 在哪",
        expected_paths=[f"{_GSON}/stream/JsonReader.java"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "流式读取 JSON 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_stream_writer",
        description="中文 NL：流式写 JSON 在哪",
        expected_paths=[f"{_GSON}/stream/JsonWriter.java"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "流式写出 JSON 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_json_object",
        description="中文 NL：JSON 对象节点在哪",
        expected_paths=[f"{_GSON}/JsonObject.java", f"{_GSON}/JsonElement.java"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "JSON 对象节点结构在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.en_deserialize",
        description="英文 NL：deserialize JSON",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "where to deserialize JSON to Java object", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="gson.resolve.nl.cn_type_adapter",
        description="中文 NL：自定义类型适配在哪",
        expected_paths=[f"{_GSON}/TypeAdapter.java", f"{_GSON}/TypeAdapterFactory.java"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "自定义类型适配器在哪", "case_kind": "nl"},
    ),
    # ---- similar (~16%) ----
    PathSetCase(
        case_id="gson.resolve.similar.fromJson",
        description="代码片段：fromJson",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "public <T> T fromJson(String json, Class<T> classOfT) "
                "throws JsonSyntaxException {\n"
                "  Object object = fromJson(json, TypeToken.get(classOfT));\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="gson.resolve.similar.toJson",
        description="代码片段：toJson",
        expected_paths=[f"{_GSON}/Gson.java"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "public String toJson(Object src) {\n"
                "  return toJson(src, src.getClass());\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="gson.resolve.similar.builder_create",
        description="代码片段：GsonBuilder create",
        expected_paths=[f"{_GSON}/GsonBuilder.java"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "public Gson create() {\n"
                "  List<TypeAdapterFactory> factories = "
                "new ArrayList<>(this.factories);\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="gson.resolve.similar.json_parser",
        description="代码片段：JsonParser parse",
        expected_paths=[f"{_GSON}/JsonParser.java"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "public static JsonElement parseString(String json) "
                "throws JsonSyntaxException {\n"
                "  return parseReader(new StringReader(json));\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="gson.resolve.similar.type_token",
        description="代码片段：TypeToken get",
        expected_paths=[f"{_GSON}/reflect/TypeToken.java"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "public static TypeToken<?> get(Type type) {\n"
                "  return new TypeToken<>(type);\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    # ---- 难例 (~9%) ----
    PathSetCase(
        case_id="gson.resolve.hard.cn_json",
        description="难例：短中文「转成JSON」",
        expected_paths=[f"{_GSON}/Gson.java", f"{_GSON}/stream/JsonWriter.java"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "转成JSON", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="gson.resolve.hard.parse_ambiguous",
        description="难例：parse 多处同名",
        expected_paths=[f"{_GSON}/JsonParser.java", f"{_GSON}/Gson.java"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=8,
        extra={"query": "parse", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="gson.resolve.hard.cn_read",
        description="难例：短中文「读JSON」",
        expected_paths=[
            f"{_GSON}/stream/JsonReader.java",
            f"{_GSON}/JsonParser.java",
            f"{_GSON}/Gson.java",
        ],
        min_precision=0.1,
        min_recall=0.33,
        top_k=10,
        extra={"query": "读JSON", "case_kind": "hard"},
    ),
]
