"""Django 开源仓 resolve GT（Agent 向配比）。

目标分布约：纯符号 25–30% | 符号+NL 15–20% | 纯 NL 30–35% | similar 15–20% | 难例 10–15%。
范围：整包 django/。
"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


DJANGO_RESOLVE_CASES = [
    # ---- 纯符号 (~25%) ----
    PathSetCase(
        case_id="django.resolve.related.Model",
        description="纯符号：Model",
        expected_paths=["django/db/models/base.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Model", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="django.resolve.related.QuerySet",
        description="纯符号：QuerySet",
        expected_paths=["django/db/models/query.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "QuerySet", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="django.resolve.related.HttpRequest",
        description="纯符号：HttpRequest",
        expected_paths=["django/http/request.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "HttpRequest", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="django.resolve.related.HttpResponse",
        description="纯符号：HttpResponse",
        expected_paths=["django/http/response.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "HttpResponse", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="django.resolve.related.AuthenticationMiddleware",
        description="纯符号：AuthenticationMiddleware",
        expected_paths=["django/contrib/auth/middleware.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "AuthenticationMiddleware", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="django.resolve.related.authenticate",
        description="纯符号：authenticate",
        expected_paths=["django/contrib/auth/__init__.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "authenticate", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="django.resolve.related.AdminSite",
        description="纯符号：AdminSite",
        expected_paths=["django/contrib/admin/sites.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "AdminSite", "expect_intent": "related", "case_kind": "sym"},
    ),
    PathSetCase(
        case_id="django.resolve.related.URLResolver",
        description="纯符号：URLResolver",
        expected_paths=["django/urls/resolvers.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "URLResolver", "expect_intent": "related", "case_kind": "sym"},
    ),
    # ---- 符号 + NL (~19%) ----
    PathSetCase(
        case_id="django.resolve.related.User",
        description="符号+NL：User 用户模型",
        expected_paths=["django/contrib/auth/models.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "User 用户模型在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="django.resolve.related.login",
        description="符号+NL：login 登录",
        expected_paths=["django/contrib/auth/__init__.py"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "login 用户登录函数在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="django.resolve.related.SessionMiddleware",
        description="符号+NL：SessionMiddleware",
        expected_paths=["django/contrib/sessions/middleware.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "SessionMiddleware 会话中间件在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="django.resolve.related.Form",
        description="符号+NL：Form 表单基类",
        expected_paths=["django/forms/forms.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Form 表单基类在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="django.resolve.related.Manager",
        description="符号+NL：Manager 模型管理器",
        expected_paths=["django/db/models/manager.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Manager 模型管理器在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    PathSetCase(
        case_id="django.resolve.related.JsonResponse",
        description="符号+NL：JsonResponse",
        expected_paths=["django/http/response.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "JsonResponse JSON 响应在哪", "expect_intent": "related", "case_kind": "sym_nl"},
    ),
    # ---- 纯 NL (~31%) ----
    PathSetCase(
        case_id="django.resolve.nl.cn_orm",
        description="中文 NL：ORM 模型基类在哪",
        expected_paths=["django/db/models/base.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "ORM 模型基类在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_auth",
        description="中文 NL：用户认证在哪",
        expected_paths=[
            "django/contrib/auth/models.py",
            "django/contrib/auth/__init__.py",
            "django/contrib/auth/middleware.py",
        ],
        min_precision=0.1,
        min_recall=0.33,
        top_k=10,
        extra={"query": "用户认证在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_queryset",
        description="中文 NL：数据库查询集合在哪",
        expected_paths=["django/db/models/query.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "数据库查询集合在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_middleware",
        description="中文 NL：认证中间件在哪",
        expected_paths=["django/contrib/auth/middleware.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "认证中间件在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_forms",
        description="中文 NL：表单基类在哪",
        expected_paths=["django/forms/forms.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "表单基类在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_url_resolve",
        description="中文 NL：URL 路由解析在哪",
        expected_paths=["django/urls/resolvers.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "URL 路由解析在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_admin",
        description="中文 NL：后台管理站点在哪",
        expected_paths=["django/contrib/admin/sites.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "后台管理站点在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_session",
        description="中文 NL：会话中间件在哪",
        expected_paths=["django/contrib/sessions/middleware.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "会话中间件在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_request",
        description="中文 NL：HTTP 请求对象在哪",
        expected_paths=["django/http/request.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 请求对象在哪", "expect_intent": "related", "case_kind": "nl"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.en_orm_save",
        description="英文 NL：persist model instance",
        expected_paths=["django/db/models/base.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "where does django save a model instance to the database", "expect_intent": "related", "case_kind": "nl"},
    ),
    # ---- similar (~16%) ----
    PathSetCase(
        case_id="django.resolve.similar.model_class",
        description="代码片段：class Model",
        expected_paths=["django/db/models/base.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "class Model(AltersData, metaclass=ModelBase):\n"
                "    def __init__(self, *args, **kwargs):\n"
                "        cls = self.__class__\n"
                "        opts = self._meta\n"
                "        _setattr = setattr\n"
            ),
            "expect_intent": "similar",
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="django.resolve.similar.authenticate",
        description="代码片段：authenticate",
        expected_paths=["django/contrib/auth/__init__.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "def authenticate(request=None, **credentials):\n"
                "    for backend, backend_path in _get_backends(return_tuples=True):\n"
                "        try:\n"
                "            user = backend.authenticate(request, **credentials)\n"
            ),
            "expect_intent": "similar",
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="django.resolve.similar.form_class",
        description="代码片段：class Form",
        expected_paths=["django/forms/forms.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "class BaseForm:\n"
                "    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None):\n"
                "        self.is_bound = data is not None or files is not None\n"
            ),
            "expect_intent": "similar",
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="django.resolve.similar.queryset_filter",
        description="代码片段：QuerySet.filter",
        expected_paths=["django/db/models/query.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "def filter(self, *args, **kwargs):\n"
                "    return self._filter_or_exclude(False, args, kwargs)\n"
            ),
            "expect_intent": "similar",
            "case_kind": "similar",
        },
    ),
    PathSetCase(
        case_id="django.resolve.similar.url_resolve",
        description="代码片段：URLResolver.resolve",
        expected_paths=["django/urls/resolvers.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "def resolve(self, path):\n"
                "    path = str(path)\n"
                "    match = self.regex.search(path)\n"
            ),
            "expect_intent": "similar",
            "case_kind": "similar",
        },
    ),
    # ---- 难例 (~12%) ----
    PathSetCase(
        case_id="django.resolve.hard.ambiguous_view",
        description="难例：View 同名多处，期望 generic base",
        expected_paths=["django/views/generic/base.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={"query": "View", "expect_intent": "related", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="django.resolve.hard.ambiguous_field",
        description="难例：Field 同名多处，期望 models.fields",
        expected_paths=["django/db/models/fields/__init__.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={"query": "Field", "expect_intent": "related", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="django.resolve.hard.short_cn_login",
        description="难例：短中文「登录」",
        expected_paths=["django/contrib/auth/__init__.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "登录", "expect_intent": "related", "case_kind": "hard"},
    ),
    PathSetCase(
        case_id="django.resolve.hard.cn_handler",
        description="难例：请求处理入口（BaseHandler）",
        expected_paths=["django/core/handlers/base.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "WSGI 请求处理入口在哪", "expect_intent": "related", "case_kind": "hard"},
    ),
]
