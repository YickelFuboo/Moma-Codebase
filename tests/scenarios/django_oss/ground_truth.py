"""Django 开源仓 resolve GT：覆盖 db / http / contrib / forms / urls / views / middleware。"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


DJANGO_RESOLVE_CASES = [
    # ---- db / ORM ----
    PathSetCase(
        case_id="django.resolve.related.Model",
        description="纯符号：Model",
        expected_paths=["django/db/models/base.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Model", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.QuerySet",
        description="纯符号：QuerySet",
        expected_paths=["django/db/models/query.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "QuerySet", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.Manager",
        description="纯符号：Manager",
        expected_paths=["django/db/models/manager.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Manager", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.Field",
        description="纯符号：Field",
        expected_paths=["django/db/models/fields/__init__.py"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Field", "expect_intent": "related"},
    ),
    # ---- http ----
    PathSetCase(
        case_id="django.resolve.related.HttpRequest",
        description="纯符号：HttpRequest",
        expected_paths=["django/http/request.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "HttpRequest", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.HttpResponse",
        description="纯符号：HttpResponse",
        expected_paths=["django/http/response.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "HttpResponse", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.JsonResponse",
        description="纯符号：JsonResponse",
        expected_paths=["django/http/response.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "JsonResponse", "expect_intent": "related"},
    ),
    # ---- contrib / auth ----
    PathSetCase(
        case_id="django.resolve.related.User",
        description="中文+符号：User 认证模型",
        expected_paths=["django/contrib/auth/models.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "User 用户模型在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.AuthenticationMiddleware",
        description="纯符号：AuthenticationMiddleware",
        expected_paths=["django/contrib/auth/middleware.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "AuthenticationMiddleware", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.authenticate",
        description="纯符号：authenticate",
        expected_paths=["django/contrib/auth/__init__.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "authenticate", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.login",
        description="中文+符号：login 登录",
        expected_paths=["django/contrib/auth/__init__.py"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=5,
        extra={"query": "login 用户登录函数在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.AdminSite",
        description="纯符号：AdminSite",
        expected_paths=["django/contrib/admin/sites.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "AdminSite", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.SessionMiddleware",
        description="纯符号：SessionMiddleware",
        expected_paths=["django/contrib/sessions/middleware.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "SessionMiddleware", "expect_intent": "related"},
    ),
    # ---- forms / urls / views / middleware / core ----
    PathSetCase(
        case_id="django.resolve.related.Form",
        description="纯符号：Form",
        expected_paths=["django/forms/forms.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "Form", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.URLResolver",
        description="纯符号：URLResolver",
        expected_paths=["django/urls/resolvers.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "URLResolver", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.View",
        description="纯符号：View",
        expected_paths=["django/views/generic/base.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "View", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.CommonMiddleware",
        description="纯符号：CommonMiddleware",
        expected_paths=["django/middleware/common.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={"query": "CommonMiddleware", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.related.BaseHandler",
        description="纯符号：BaseHandler",
        expected_paths=["django/core/handlers/base.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={"query": "BaseHandler", "expect_intent": "related"},
    ),
    # ---- 中文 NL ----
    PathSetCase(
        case_id="django.resolve.nl.cn_orm",
        description="中文 NL：ORM 模型基类在哪",
        expected_paths=["django/db/models/base.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "ORM 模型基类在哪", "expect_intent": "related"},
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
        extra={"query": "用户认证在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_queryset",
        description="中文 NL：数据库查询集合在哪",
        expected_paths=["django/db/models/query.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "数据库查询集合 QuerySet 在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_middleware",
        description="中文 NL：认证中间件在哪",
        expected_paths=["django/contrib/auth/middleware.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "认证中间件在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_forms",
        description="中文 NL：表单基类在哪",
        expected_paths=["django/forms/forms.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "表单 Form 基类在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_url_resolve",
        description="中文 NL：URL 路由解析在哪",
        expected_paths=["django/urls/resolvers.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "URL 路由解析在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_admin",
        description="中文 NL：后台管理站点在哪",
        expected_paths=["django/contrib/admin/sites.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "后台管理 AdminSite 在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_session",
        description="中文 NL：会话中间件在哪",
        expected_paths=["django/contrib/sessions/middleware.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "会话 Session 中间件在哪", "expect_intent": "related"},
    ),
    PathSetCase(
        case_id="django.resolve.nl.cn_request",
        description="中文 NL：HTTP 请求对象在哪",
        expected_paths=["django/http/request.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"query": "HTTP 请求对象在哪", "expect_intent": "related"},
    ),
    # ---- similar ----
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
        },
    ),
]
