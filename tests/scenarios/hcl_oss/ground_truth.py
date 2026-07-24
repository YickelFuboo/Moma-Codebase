"""HashiCorp HCL resolve GT（Agent 向配比）。

目标：纯符号 25–30% | 符号+NL 15–20% | 纯 NL 30–35% | similar 15–20% | 难例 10–15%。
本文件 32 条：sym8 / sym_nl6 / nl10 / similar5 / hard3。
"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


HCL_RESOLVE_CASES = [
    # ---- 纯符号 (~25%) ----
    PathSetCase(
        case_id="hcl.resolve.related.ParseHCL",
        description="纯符号：ParseHCL",
        expected_paths=["hclparse/parser.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "ParseHCL", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.NewParser",
        description="纯符号：NewParser",
        expected_paths=["hclparse/parser.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "NewParser", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.Diagnostic",
        description="纯符号：Diagnostic",
        expected_paths=["diagnostic.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Diagnostic", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.EvalContext",
        description="纯符号：EvalContext",
        expected_paths=["eval_context.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "EvalContext", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.BodyContent",
        description="纯符号：BodyContent / structure",
        expected_paths=["structure.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "BodyContent", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.ParseJSON",
        description="纯符号：json.Parse",
        expected_paths=["json/public.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Parse", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.hclsimple_Decode",
        description="纯符号：hclsimple.Decode",
        expected_paths=["hclsimple/hclsimple.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "DecodeFile", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.gohcl_Decode",
        description="纯符号：gohcl Decode",
        expected_paths=["gohcl/decode.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "DecodeBody", "case_kind": "sym"},
    ),
    # ---- 符号+NL (~19%) ----
    PathSetCase(
        case_id="hcl.resolve.related.ParseHCL_nl",
        description="符号+NL：ParseHCL 解析入口",
        expected_paths=["hclparse/parser.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "ParseHCL 解析 HCL 入口在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.ParseJSON_nl",
        description="符号+NL：ParseJSON",
        expected_paths=["hclparse/parser.go", "json/public.go"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "ParseJSON JSON 配置解析在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.hclsyntax_parser",
        description="符号+NL：原生语法 parser",
        expected_paths=["hclsyntax/parser.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "hclsyntax parser 原生语法解析在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.Diagnostic_nl",
        description="符号+NL：Diagnostic 诊断",
        expected_paths=["diagnostic.go", "diagnostic_text.go"],
        min_precision=0.15,
        min_recall=0.5,
        top_k=5,
        extra={"query": "Diagnostic 诊断错误结构在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.hclwrite_nl",
        description="符号+NL：hclwrite 写出",
        expected_paths=["hclwrite/public.go", "hclwrite/generate.go", "hclwrite/ast.go"],
        min_precision=0.15,
        min_recall=0.33,
        top_k=5,
        extra={"query": "hclwrite 写出 HCL 在哪", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.related.EvalContext_nl",
        description="符号+NL：EvalContext 求值上下文",
        expected_paths=["eval_context.go"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "EvalContext 求值上下文在哪", "case_kind": "sym_nl"},
    ),
    # ---- 纯 NL (~31%) ----
    PathSetCase(
        case_id="hcl.resolve.nl.cn_parse_hcl",
        description="中文 NL：解析 HCL 文件在哪",
        expected_paths=["hclparse/parser.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "解析 HCL 配置文件入口在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_diagnostic",
        description="中文 NL：诊断错误信息在哪",
        expected_paths=["diagnostic.go", "diagnostic_text.go"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "诊断错误信息 Diagnostic 在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_decode_struct",
        description="中文 NL：解码到 Go 结构体在哪",
        expected_paths=["gohcl/decode.go", "hclsimple/hclsimple.go"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "把 HCL 解码到 Go 结构体在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_write_hcl",
        description="中文 NL：生成/写出 HCL 在哪",
        expected_paths=["hclwrite/ast.go", "hclwrite/generate.go", "hclwrite/public.go"],
        min_precision=0.1,
        min_recall=0.33,
        top_k=10,
        extra={"query": "写出或生成 HCL 配置在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_json_syntax",
        description="中文 NL：JSON 语法解析在哪",
        expected_paths=["json/public.go", "json/parser.go"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "HCL JSON 语法解析在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_native_syntax",
        description="中文 NL：原生语法解析在哪",
        expected_paths=["hclsyntax/parser.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HCL 原生语法解析器在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_simple_decode",
        description="中文 NL：简单一键解码在哪",
        expected_paths=["hclsimple/hclsimple.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "简单一键解码 HCL 文件在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_eval_context",
        description="中文 NL：表达式求值上下文在哪",
        expected_paths=["eval_context.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "表达式求值上下文在哪", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.en_parse_file",
        description="英文 NL：parse configuration file",
        expected_paths=["hclparse/parser.go", "hclsimple/hclsimple.go"],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={"query": "where to parse an HCL configuration file", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="hcl.resolve.nl.cn_body_schema",
        description="中文 NL：Body schema / 结构在哪",
        expected_paths=["structure.go"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "Body 内容结构 schema 在哪", "case_kind": "nl"},
    ),
    # ---- similar (~16%) ----
    PathSetCase(
        case_id="hcl.resolve.similar.new_parser",
        description="代码片段：NewParser",
        expected_paths=["hclparse/parser.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "func NewParser() *Parser {\n"
                "\treturn &Parser{\n"
                "\t\tfiles: map[string]*hcl.File{},\n"
                "\t}\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="hcl.resolve.similar.parse_hcl",
        description="代码片段：ParseHCL 方法",
        expected_paths=["hclparse/parser.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "func (p *Parser) ParseHCL(src []byte, filename string) (*hcl.File, hcl.Diagnostics) {\n"
                "\tfile, diags := hclsyntax.ParseConfig(src, filename, hcl.Pos{Byte: 0, Line: 1, Column: 1})\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="hcl.resolve.similar.hclsimple_decode",
        description="代码片段：hclsimple.Decode",
        expected_paths=["hclsimple/hclsimple.go"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "func Decode(filename string, src []byte, ctx *hcl.EvalContext, target interface{}) error {\n"
                "\tfile, diags := hclsyntax.ParseConfig(src, filename, hcl.Pos{Line: 1, Column: 1})\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="hcl.resolve.similar.json_parse",
        description="代码片段：json.Parse",
        expected_paths=["json/public.go"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "func Parse(src []byte, filename string) (*hcl.File, hcl.Diagnostics) {\n"
                "\treturn ParseWithStartPos(src, filename, hcl.Pos{Byte: 0, Line: 1, Column: 1})\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="hcl.resolve.similar.diagnostic_text",
        description="代码片段：诊断文本渲染弱改写",
        expected_paths=["diagnostic_text.go", "diagnostic.go"],
        min_precision=0.2,
        min_recall=0.5,
        top_k=3,
        extra={
            "query": (
                "func (d Diagnostic) Error() string {\n"
                "\treturn FormatDiagnostic(d)\n"
                "}\n"
            ),
            "case_kind": "similar",
        },
    ),
    # ---- 难例 (~9%) ----
    PathSetCase(
        case_id="hcl.resolve.hard.cn_parse",
        description="难例：短中文「解析配置」",
        expected_paths=["hclparse/parser.go", "hclsyntax/parser.go", "json/public.go"],
        min_precision=0.1,
        min_recall=0.33,
        top_k=10,
        extra={"query": "解析配置", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="hcl.resolve.hard.Decode_ambiguous",
        description="难例：Decode 多包同名",
        expected_paths=["gohcl/decode.go", "hclsimple/hclsimple.go", "hcldec/decode.go"],
        min_precision=0.1,
        min_recall=0.33,
        top_k=8,
        extra={"query": "Decode", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="hcl.resolve.hard.cn_write",
        description="难例：短中文「写出配置」",
        expected_paths=["hclwrite/public.go", "hclwrite/generate.go", "hclwrite/ast.go"],
        min_precision=0.1,
        min_recall=0.33,
        top_k=10,
        extra={"query": "写出配置", "case_kind": "hard"},
    ),
]
