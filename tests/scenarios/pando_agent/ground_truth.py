"""Pando-Agent 全仓 related/hybrid 与 similar 评测 ground truth。"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase, SymbolRelationCase, TitleSetCase


PANDO_RELATED_CASES = [
    PathSetCase(
        case_id="pando.full.exact.ReActAgent",
        description="全仓精确符号 ReActAgent",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["ReActAgent"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="pando.full.exact.BaseAgent",
        description="全仓精确符号 BaseAgent",
        expected_paths=["app/agents/core/base.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["BaseAgent"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="pando.full.exact.ContextBuilder",
        description="全仓精确符号 ContextBuilder",
        expected_paths=["app/agents/context/context.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["ContextBuilder"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="pando.full.exact.PlanningAgent",
        description="全仓精确符号 PlanningAgent",
        expected_paths=["app/agents/plan/planning.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["PlanningAgent"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="pando.full.exact.LangGraphExecutor",
        description="全仓精确符号 LangGraphExecutor",
        expected_paths=["app/agents/plan/langraph_excutor.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["LangGraphExecutor"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="pando.full.exact.EmbeddingModelFactory",
        description="全仓精确符号 EmbeddingModelFactory",
        expected_paths=["app/infrastructure/llms/embedding_models/factory.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["EmbeddingModelFactory"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="pando.full.exact.OpenAIModels",
        description="全仓精确符号 OpenAIModels",
        expected_paths=["app/infrastructure/llms/chat_models/openai_llm.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["OpenAIModels"], "expect_exact": True},
    ),
    PathSetCase(
        case_id="pando.full.path.jwt_validator",
        description="路径段 jwt_validator 应命中鉴权模块",
        expected_paths=["app/utils/auth/jwt_validator.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["jwt_validator"]},
    ),
    PathSetCase(
        case_id="pando.full.semantic.memory",
        description="语义检索默认记忆实现",
        expected_paths=["app/agents/memorys/default/memory.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=15,
        extra={"keywords": ["default memory extract prompt for agent long-term memory"]},
    ),
    PathSetCase(
        case_id="pando.full.semantic.websocket",
        description="语义检索 websocket 通道",
        expected_paths=[
            "app/channel/websocket/websocket.py",
            "app/channel/websocket/manager.py",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=15,
        extra={"keywords": ["websocket channel connection manager for realtime messages"]},
    ),
    PathSetCase(
        case_id="pando.related.hard.short.cn_memory",
        description="短中文难例：记忆",
        expected_paths=["app/agents/memorys/default/memory.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["记忆"]},
    ),
    PathSetCase(
        case_id="pando.related.hard.short.cn_auth",
        description="短中文难例：鉴权",
        expected_paths=[
            "app/utils/auth/jwt_validator.py",
            "app/utils/auth/jwt_middleware.py",
        ],
        min_precision=0.15,
        min_recall=0.5,
        top_k=10,
        extra={"keywords": ["鉴权"]},
    ),
    PathSetCase(
        case_id="pando.related.hard.short.cn_ws",
        description="短中文难例：websocket",
        expected_paths=[
            "app/channel/websocket/websocket.py",
            "app/channel/websocket/manager.py",
        ],
        min_precision=0.15,
        min_recall=0.5,
        top_k=10,
        extra={"keywords": ["websocket 通道"]},
    ),
]

# Agent 主路径 search resolve：覆盖符号 exact / 中文 NL / 代码 similar
# 消融对比以本列表为准（比旧 6 案更能拉开「有无符号摘要」差距）
PANDO_RESOLVE_CASES = [
    PathSetCase(
        case_id="pando.resolve.related.ReActAgent",
        description="中文+符号：resolve 应走 related 并命中 react.py",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "查找 ReActAgent 实现位置",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.BaseAgent",
        description="纯符号：BaseAgent 定义",
        expected_paths=["app/agents/core/base.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "BaseAgent",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.ContextBuilder",
        description="纯符号：ContextBuilder",
        expected_paths=["app/agents/context/context.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "ContextBuilder",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.PlanningAgent",
        description="中文+符号：PlanningAgent 在哪",
        expected_paths=["app/agents/plan/planning.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "PlanningAgent 实现在哪",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.LangGraphExecutor",
        description="纯符号：LangGraphExecutor",
        expected_paths=["app/agents/plan/langraph_excutor.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "LangGraphExecutor",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.EmbeddingModelFactory",
        description="纯符号：EmbeddingModelFactory",
        expected_paths=["app/infrastructure/llms/embedding_models/factory.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "EmbeddingModelFactory",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.OpenAIModels",
        description="纯符号：OpenAIModels",
        expected_paths=["app/infrastructure/llms/chat_models/openai_llm.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "OpenAIModels",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.jwt_validator",
        description="路径/标识：jwt_validator",
        expected_paths=["app/utils/auth/jwt_validator.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "jwt_validator",
            "expect_intent": "related",
            "expect_channel": "related",
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.nl.semantic.memory",
        description="弱语义 NL：记忆相关应命中 memory.py",
        expected_paths=["app/agents/memorys/default/memory.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=10,
        extra={
            "query": "default memory extract prompt for agent long-term memory",
            "expect_intent": "related",
            "expect_channels_any": ["related", "similar", "grep"],
        },
    ),
    PathSetCase(
        case_id="pando.resolve.nl.semantic.websocket",
        description="弱语义 NL：websocket channel manager",
        expected_paths=[
            "app/channel/websocket/websocket.py",
            "app/channel/websocket/manager.py",
        ],
        min_precision=0.1,
        min_recall=0.5,
        top_k=10,
        extra={
            "query": "websocket channel connection manager for realtime messages",
            "expect_intent": "related",
            "expect_channels_any": ["related", "similar", "grep"],
        },
    ),
    PathSetCase(
        case_id="pando.resolve.nl.cn_auth",
        description="中文 NL：鉴权在哪",
        expected_paths=[
            "app/utils/auth/jwt_validator.py",
            "app/utils/auth/jwt_middleware.py",
        ],
        min_precision=0.15,
        min_recall=0.5,
        top_k=10,
        extra={
            "query": "鉴权在哪",
            "expect_intent": "related",
            "expect_channels_any": ["related", "similar", "grep"],
        },
    ),
    PathSetCase(
        case_id="pando.resolve.nl.cn_memory",
        description="短中文 NL：记忆在哪",
        expected_paths=["app/agents/memorys/default/memory.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={
            "query": "记忆在哪",
            "expect_intent": "related",
            "expect_channels_any": ["related", "similar", "grep"],
        },
    ),
    PathSetCase(
        case_id="pando.resolve.nl.cn_ws",
        description="中文 NL：websocket 通道在哪",
        expected_paths=[
            "app/channel/websocket/websocket.py",
            "app/channel/websocket/manager.py",
        ],
        min_precision=0.15,
        min_recall=0.5,
        top_k=10,
        extra={
            "query": "websocket 通道在哪",
            "expect_intent": "related",
            "expect_channels_any": ["related", "similar", "grep"],
            "expect_top1_in_expected": True,
        },
    ),
    PathSetCase(
        case_id="pando.resolve.similar.think_and_act",
        description="代码片段：think_and_act → react.py",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "async def think_and_act(self, question, run_ctx):\n"
                "    if self.tool_choices == ToolChoice.NONE:\n"
                "        content, usage = await self.think_only(question)\n"
                "        return content, [], usage, None\n"
            ),
            "expect_intent": "similar",
            "expect_channel": "similar",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.similar.agent_state",
        description="代码片段：AgentState → base.py",
        expected_paths=["app/agents/core/base.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "class AgentState(str, Enum):\n"
                '    IDLE = "IDLE"\n'
                '    RUNNING = "RUNNING"\n'
                '    WAITING = "WAITING"\n'
                '    ERROR = "ERROR"\n'
                '    FINISHED = "FINISHED"\n'
            ),
            "expect_intent": "similar",
            "expect_channel": "similar",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.similar.jwt_validator",
        description="代码片段：JWTValidator → jwt_validator.py",
        expected_paths=["app/utils/auth/jwt_validator.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "class JWTValidator:\n"
                "    def __init__(\n"
                "        self,\n"
                "        cache_ttl: int = 3600,\n"
                "        blacklist_cache_ttl: int = 300,\n"
                "    ):\n"
                "        self._user_service_url = (settings.auth_user_service_url or \"\").rstrip(\"/\")\n"
                "        self._jwks_endpoint = settings.auth_jwks_endpoint or \"/.well-known/jwks.json\"\n"
            ),
            "expect_intent": "similar",
            "expect_channel": "similar",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.similar.websocket_endpoint",
        description="代码片段：websocket_endpoint → websocket.py",
        expected_paths=["app/channel/websocket/websocket.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                '@router.websocket("/{session_id}")\n'
                "async def websocket_endpoint(websocket: WebSocket, session_id: str = None):\n"
                "    session = await SESSION_MANAGER.get_session(session_id)\n"
                "    if not session:\n"
                '        raise HTTPException(status_code=400, detail="Session not found")\n'
            ),
            "expect_intent": "similar",
            "expect_channel": "similar",
            "case_kind": "similar",
        },
    ),
    # ---- Agent 向补充：符号+NL / 难例 / 纯 NL ----
    PathSetCase(
        case_id="pando.resolve.related.ContextBuilder_nl",
        description="符号+NL：ContextBuilder 上下文拼装",
        expected_paths=["app/agents/context/context.py"],
        min_precision=0.3,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "ContextBuilder 上下文拼装在哪",
            "expect_intent": "related",
            "case_kind": "sym_nl",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.jwt_nl",
        description="符号+NL：JWT 校验器",
        expected_paths=["app/utils/auth/jwt_validator.py"],
        min_precision=0.25,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "JWTValidator 鉴权校验在哪",
            "expect_intent": "related",
            "case_kind": "sym_nl",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.nl.cn_plan",
        description="中文 NL：规划 Agent 在哪",
        expected_paths=["app/agents/plan/planning.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={
            "query": "规划 Agent 实现在哪",
            "expect_intent": "related",
            "case_kind": "nl",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.nl.cn_embedding",
        description="中文 NL：Embedding 工厂在哪",
        expected_paths=["app/infrastructure/llms/embedding_models/factory.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={
            "query": "向量 Embedding 模型工厂在哪",
            "expect_intent": "related",
            "case_kind": "nl",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.hard.short_cn_react",
        description="难例：短中文「推理执行」",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={
            "query": "推理执行",
            "expect_intent": "related",
            "case_kind": "hard",
        },
    ),
]

# Chunk similar：用接近源码的片段，期望命中定义文件（行块向量）
# 评测口径：短列表（top_k=3，检索侧常截到 1～2）；目标 Precision≥0.6 且 Recall=1.0
PANDO_SIMILAR_CASES = [
    PathSetCase(
        case_id="pando.similar.react_agent",
        description="think_and_act 片段应命中 react.py",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.6,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "async def think_and_act(\n"
                "    self,\n"
                "    question: str,\n"
                "    run_ctx: RuntimeContext,\n"
                ") -> Tuple[str, List[ToolCall], TokenUsage, Optional[List[Tuple[ToolCall, ToolResult]]]]:\n"
                '    """思考：无工具走 think_only，有工具走 think_with_act。"""\n'
                "    if self.tool_choices == ToolChoice.NONE:\n"
                "        content, usage = await self.think_only(question)\n"
                "        return content, [], usage, None\n"
                "    else:\n"
                "        content, tool_calls, usage, tool_pairs = await self.think_with_act(question, run_ctx)\n"
                "        return content, tool_calls, usage, tool_pairs\n"
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.agent_state",
        description="AgentState 枚举片段应命中 base.py",
        expected_paths=["app/agents/core/base.py"],
        min_precision=0.6,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "class AgentState(str, Enum):\n"
                '    IDLE = "IDLE"\n'
                '    RUNNING = "RUNNING"\n'
                '    WAITING = "WAITING"\n'
                '    ERROR = "ERROR"\n'
                '    FINISHED = "FINISHED"\n'
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.jwt_validator",
        description="JWTValidator 片段应命中 jwt_validator.py",
        expected_paths=["app/utils/auth/jwt_validator.py"],
        min_precision=0.6,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "class JWTValidator:\n"
                "    def __init__(\n"
                "        self,\n"
                "        cache_ttl: int = 3600,\n"
                "        blacklist_cache_ttl: int = 300,\n"
                "    ):\n"
                "        self._user_service_url = (settings.auth_user_service_url or \"\").rstrip(\"/\")\n"
                "        self._jwks_endpoint = settings.auth_jwks_endpoint or \"/.well-known/jwks.json\"\n"
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.websocket_endpoint",
        description="websocket_endpoint 片段应命中 websocket.py",
        expected_paths=["app/channel/websocket/websocket.py"],
        min_precision=0.6,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                '@router.websocket("/{session_id}")\n'
                "async def websocket_endpoint(websocket: WebSocket, session_id: str = None):\n"
                "    session = await SESSION_MANAGER.get_session(session_id)\n"
                "    if not session:\n"
                '        raise HTTPException(status_code=400, detail="Session not found")\n'
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.memory_extract",
        description="MemoryExtractPrompt 片段应命中 memory.py",
        expected_paths=["app/agents/memorys/default/memory.py"],
        min_precision=0.6,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "class MemoryExtractPrompt(BaseModel):\n"
                "    system_prompt: str = Field(...)\n"
                "    user_instruction: str = Field(...)\n"
                "\n"
                "    @classmethod\n"
                '    def for_workspace(cls) -> "MemoryExtractPrompt":\n'
                '        return cls(\n'
                '            system_prompt="""You are the workspace memory consolidation agent.\n'
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.context_builder",
        description="ContextBuilder 片段应命中 context.py",
        expected_paths=["app/agents/context/context.py"],
        min_precision=0.6,
        min_recall=1.0,
        top_k=3,
        extra={
            "code": (
                "class ContextBuilder:\n"
                "\n"
                "    def __init__(\n"
                "        self,\n"
                "        ctx: AgentContext,\n"
                "        skills_manager: SkillsManager | None = None,\n"
                "        memory_manager: BaseMemoryManager | None = None,\n"
                "    ):\n"
                "        self.ctx = ctx\n"
                "        self.skills_manager = skills_manager\n"
                "        self.memory_manager = memory_manager\n"
            ),
        },
    ),
]

# 非极强：改写/匿名化/缺省符号名，观察短列表条数与 P/R（允许略低阈值）
PANDO_SIMILAR_WEAK_CASES = [
    PathSetCase(
        case_id="pando.similar.weak.react_loop",
        description="改写 ReAct 循环逻辑（无 think_and_act 原名）",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "async def decide_next_step(self, user_question, runtime):\n"
                "    if self.tool_choices == ToolChoice.NONE:\n"
                "        text, usage = await self.think_only(user_question)\n"
                "        return text, [], usage, None\n"
                "    text, calls, usage, pairs = await self.think_with_act(user_question, runtime)\n"
                "    return text, calls, usage, pairs\n"
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.weak.jwt_auth",
        description="JWT 校验逻辑改写（无 JWTValidator 类名）",
        expected_paths=["app/utils/auth/jwt_validator.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "class TokenAuthHelper:\n"
                "    def __init__(self, cache_seconds=3600, deny_cache_seconds=300):\n"
                "        self._user_service_url = (settings.auth_user_service_url or '').rstrip('/')\n"
                "        self._jwks_endpoint = settings.auth_jwks_endpoint or '/.well-known/jwks.json'\n"
                "\n"
                "    async def verify_bearer(self, token: str):\n"
                "        keys = await self.fetch_jwks()\n"
                "        return self.decode_with_keys(token, keys)\n"
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.weak.ws_session",
        description="WebSocket 会话接入改写（无 websocket_endpoint）",
        expected_paths=["app/channel/websocket/websocket.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "async def accept_realtime_channel(ws, sid=None):\n"
                "    session = await SESSION_MANAGER.get_session(sid)\n"
                "    if session is None:\n"
                "        raise HTTPException(status_code=400, detail='Session not found')\n"
                "    await ws.accept()\n"
                "    return session\n"
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.weak.memory_prompt",
        description="工作区记忆整理 prompt 构造（无 MemoryExtractPrompt）",
        expected_paths=["app/agents/memorys/default/memory.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "def build_workspace_memory_prompt():\n"
                "    system = 'You are the workspace memory consolidation agent.'\n"
                "    user = 'Extract durable facts from the conversation into memory.'\n"
                "    return {'system_prompt': system, 'user_instruction': user}\n"
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.weak.context_skills",
        description="上下文拼装改写（无 ContextBuilder）",
        expected_paths=["app/agents/context/context.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "class PromptAssembler:\n"
                "    def __init__(self, agent_ctx, skills=None, mem=None):\n"
                "        self.ctx = agent_ctx\n"
                "        self.skills_manager = skills\n"
                "        self.memory_manager = mem\n"
                "\n"
                "    def assemble(self, question: str) -> str:\n"
                "        parts = [self.ctx.system_prompt, question]\n"
                "        if self.skills_manager:\n"
                "            parts.append(self.skills_manager.render())\n"
                "        return '\\n'.join(parts)\n"
            ),
        },
    ),
    PathSetCase(
        case_id="pando.similar.weak.planning_run",
        description="规划执行改写（贴近 PlanningAgent.run）",
        expected_paths=["app/agents/plan/planning.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=3,
        extra={
            "signal": "weak",
            "code": (
                "class TaskPlanner(BaseAgent):\n"
                "    async def run(self, question: str, *, is_internal: bool = False) -> str:\n"
                "        plan = await self.build_plan(question)\n"
                "        for step in plan.steps:\n"
                "            await self.execute_step(step)\n"
                "        return plan.summary\n"
            ),
        },
    ),
]

# MR experience pattern：强特征 query → 期望标题子串；评测 Top1 + 标题集合 P/R
# 弱短词（如 jwt/鉴权）当前召回不稳，不纳入本轮 GT
PANDO_PATTERN_CASES = [
    TitleSetCase(
        case_id="pando.pattern.skill_hub",
        description="Skill Hub 注册发现",
        expected_titles=["Skills Hub"],
        min_precision=0.33,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": "Skill Hub 统一管理注册发现",
            "require_top1": True,
        },
    ),
    TitleSetCase(
        case_id="pando.pattern.skill_migrate",
        description="Skill 私有目录迁移到公共目录",
        expected_titles=["私有目录迁移"],
        min_precision=0.33,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": "Skill 从私有目录迁移到公共目录",
            "require_top1": True,
        },
    ),
    TitleSetCase(
        case_id="pando.pattern.agent_bus",
        description="Agent 核心与子 Agent 总线解耦",
        expected_titles=["消息总线"],
        min_precision=0.33,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": "Agent 核心与子 Agent 总线解耦",
            "require_top1": True,
        },
    ),
    TitleSetCase(
        case_id="pando.pattern.streaming",
        description="流式输出全链路",
        expected_titles=["流式输出跨层贯通"],
        min_precision=0.33,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": "流式输出全链路贯通前端渲染",
            "require_top1": True,
        },
    ),
    TitleSetCase(
        case_id="pando.pattern.prompt_layers",
        description="prompt 按职责分层",
        expected_titles=["prompt 按关注点三层分离"],
        min_precision=0.33,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": "prompt 按职责分层 AGENT USER TOOLS",
            "require_top1": True,
        },
    ),
    TitleSetCase(
        case_id="pando.pattern.web_providers",
        description="多 Provider Web 抓取可插拔",
        expected_titles=["多 Provider"],
        min_precision=0.33,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": "多 Provider 可插拔 Web 抓取",
            "require_top1": True,
        },
    ),
    TitleSetCase(
        case_id="pando.pattern.memory",
        description="记忆层拆分/提取相关经验",
        expected_titles=["Memory"],
        min_precision=0.33,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": "记忆提取",
            "require_top1": True,
        },
    ),
]

# ---------- Graph callers（开源 CodeGraph；expected 为调用方文件）----------

PANDO_CALLERS_CASES = [
    SymbolRelationCase(
        case_id="pando.graph.callers.ReActAgent",
        description="ReActAgent 的 callers 应含执行器/子代理",
        symbol="ReActAgent",
        expected_paths=[
            "app/agents/plan/react_executor.py",
            "app/agents/core/subagent.py",
        ],
        min_precision=0.4,
        min_recall=1.0,
        limit=15,
    ),
    SymbolRelationCase(
        case_id="pando.graph.callers.ContextBuilder",
        description="ContextBuilder 的 callers 应含 react/planning",
        symbol="ContextBuilder",
        expected_paths=[
            "app/agents/core/react.py",
            "app/agents/plan/planning.py",
        ],
        min_precision=0.4,
        min_recall=1.0,
        limit=15,
    ),
    SymbolRelationCase(
        case_id="pando.graph.callers.BaseAgent",
        description="BaseAgent 的 callers 应含 react/planning",
        symbol="BaseAgent",
        expected_paths=[
            "app/agents/core/react.py",
            "app/agents/plan/planning.py",
        ],
        min_precision=0.4,
        min_recall=1.0,
        limit=15,
    ),
    SymbolRelationCase(
        case_id="pando.graph.callers.jwt_validator",
        description="jwt_validator 的 callers 应含 middleware",
        symbol="jwt_validator",
        expected_paths=[
            "app/utils/auth/jwt_middleware.py",
        ],
        min_precision=0.5,
        min_recall=1.0,
        limit=10,
    ),
    SymbolRelationCase(
        case_id="pando.graph.callers.PlanningAgent",
        description="PlanningAgent 的 callers 应含 bus/queues 或 plan 包入口",
        symbol="PlanningAgent",
        expected_paths=[
            "app/agents/bus/queues.py",
            "app/agents/plan/__init__.py",
        ],
        min_precision=0.3,
        min_recall=0.5,
        limit=10,
    ),
]
