"""KnowledegBase-Service：related / similar 难例 ground truth。"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase


KB_RELATED_CASES = [
    PathSetCase(
        case_id="kb.related.exact.KBService",
        description="精确符号 KBService",
        expected_paths=["app/domains/services/kb_service.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["KBService"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="kb.related.exact.DocParserService",
        description="精确符号 DocParserService",
        expected_paths=["app/domains/services/doc_parser_service.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["DocParserService"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="kb.related.exact.SessionManager",
        description="精确符号 SessionManager",
        expected_paths=["app/agent_frame/session/manager.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["SessionManager"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="kb.related.exact.Dealer",
        description="精确符号检索 Dealer（rag retrieval）",
        expected_paths=["app/rag_core/rag/retrieval/search.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["Dealer"], "expect_exact": False},
    ),
    PathSetCase(
        case_id="kb.related.hard.short.cn_kb",
        description="短中文：知识库服务",
        expected_paths=["app/domains/services/kb_service.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["知识库服务"]},
    ),
    PathSetCase(
        case_id="kb.related.hard.short.cn_parse",
        description="短中文：文档解析",
        expected_paths=["app/domains/services/doc_parser_service.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["文档解析"]},
    ),
    PathSetCase(
        case_id="kb.related.hard.semantic_retrieval",
        description="自然语言：向量检索重排",
        expected_paths=["app/rag_core/rag/retrieval/search.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=15,
        extra={"keywords": ["document retrieval rerank vector search dealer"]},
    ),
    PathSetCase(
        case_id="kb.related.hard.session",
        description="自然语言：会话管理创建 session",
        expected_paths=["app/agent_frame/session/manager.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=15,
        extra={"keywords": ["agent session create_session storage manager"]},
    ),
]

KB_SIMILAR_CASES = [
    PathSetCase(
        case_id="kb.similar.kb_service_create",
        description="创建知识库片段应命中 kb_service.py",
        expected_paths=["app/domains/services/kb_service.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "class KBService:\n"
                "    @staticmethod\n"
                "    async def create_kb(\n"
                "        session: AsyncSession,\n"
                "        name: str,\n"
                "        owner_id: str,\n"
                "        description: str = None,\n"
                "        language: str = \"Chinese\",\n"
                "        tenant_id: str = None,\n"
                "    ) -> KB:\n"
                "        if not tenant_id:\n"
                "            raise ValueError(\"缺少租户信息\")\n"
            ),
        },
    ),
    PathSetCase(
        case_id="kb.similar.session_manager",
        description="SessionManager.create_session 片段",
        expected_paths=["app/agent_frame/session/manager.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "class SessionManager:\n"
                "    async def create_session(\n"
                "        self,\n"
                "        session_type: str,\n"
                "        user_id: str = \"anonymous\",\n"
                "        description: str = \"\",\n"
                "        metadata: Optional[Dict[str, Any]] = None,\n"
                "        llm_name: Optional[str] = None\n"
                "    ) -> str:\n"
                "        session_id = f\"session_{timestamp}_{random_suffix}\"\n"
            ),
        },
    ),
    PathSetCase(
        case_id="kb.similar.dealer_get_vector",
        description="Dealer._get_vector 片段应命中 search.py",
        expected_paths=["app/rag_core/rag/retrieval/search.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "class Dealer:\n"
                "    async def _get_vector(self, txt, emb_mdl, topk=10, similarity=0.1):\n"
                "        qv, _ = await emb_mdl.encode_queries(txt)\n"
                "        embedding_data = [get_float(v) for v in qv]\n"
                "        vector_column_name = f\"q_{len(embedding_data)}_vec\"\n"
                "        return MatchDenseExpr(vector_column_name, embedding_data, 'float', 'cosine', topk)\n"
            ),
        },
    ),
]

KB_SIMILAR_WEAK_CASES = [
    PathSetCase(
        case_id="kb.similar.weak.create_kb",
        description="创建知识库改写（无 KBService 类名）",
        expected_paths=["app/domains/services/kb_service.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "async def make_knowledge_base(db, title, owner, tenant):\n"
                "    if not tenant:\n"
                "        raise ValueError('缺少租户信息')\n"
                "    if await name_exists_in_tenant(db, title, tenant):\n"
                "        raise ValueError('知识库名称已存在')\n"
                "    embd_provider_name, embd_model_name = embedding_factory.get_default_model()\n"
                "    return await persist_kb(db, title, owner, tenant, embd_provider_name, embd_model_name)\n"
            ),
        },
    ),
    PathSetCase(
        case_id="kb.similar.weak.session_create",
        description="会话创建改写（无 SessionManager）",
        expected_paths=["app/agent_frame/session/manager.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "async def open_chat_session(store, kind, uid='anonymous'):\n"
                "    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')\n"
                "    random_suffix = uuid.uuid4().hex[:8]\n"
                "    sid = f'session_{timestamp}_{random_suffix}'\n"
                "    record = Session(session_id=sid, user_id=uid, session_type=kind)\n"
                "    await store.save(record)\n"
                "    return sid\n"
            ),
        },
    ),
    PathSetCase(
        case_id="kb.similar.weak.retrieval_vector",
        description="检索向量构造改写（无 Dealer）",
        expected_paths=["app/rag_core/rag/retrieval/search.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "async def build_dense_match(text, embedder, topk=10, similarity=0.1):\n"
                "    qv, _ = await embedder.encode_queries(text)\n"
                "    embedding_data = [get_float(v) for v in qv]\n"
                "    col = f'q_{len(embedding_data)}_vec'\n"
                "    return MatchDenseExpr(col, embedding_data, 'float', 'cosine', topk, {'similarity': similarity})\n"
            ),
        },
    ),
]
