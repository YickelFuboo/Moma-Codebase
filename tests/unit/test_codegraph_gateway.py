import app.repo_analysis.services.codegraph.gateway as gateway_mod
import app.repo_analysis.services.codegraph.providers.builtin.provider as builtin_mod
from app.repo_analysis.services.codegraph.base import (
    CodeGraphGeneratorBase,
    CodeGraphProvider,
    CodeGraphSearchBase,
)
from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
from app.repo_analysis.services.codegraph.providers import PROVIDER_REGISTRY, create_provider
from app.repo_analysis.services.codegraph.providers.builtin.provider import BuiltinCodeGraphProvider
from app.repo_analysis.services.codegraph.providers.codegraph.provider import CodeGraphCliProvider


class TestCodeGraphProviderRegistry:
    def test_registry_contains_builtin_and_codegraph(self):
        assert set(PROVIDER_REGISTRY.keys()) == {"builtin", "codegraph"}

    def test_create_provider_builtin(self):
        provider = create_provider("builtin")
        assert isinstance(provider, BuiltinCodeGraphProvider)
        assert provider.name == "builtin"
        assert isinstance(provider, CodeGraphProvider)

    def test_create_provider_codegraph(self):
        provider = create_provider("codegraph")
        assert isinstance(provider, CodeGraphCliProvider)
        assert provider.name == "codegraph"
        assert isinstance(provider, CodeGraphProvider)

    def test_create_provider_unknown(self):
        try:
            create_provider("unknown-x")
            assert False, "should raise"
        except ValueError as exc:
            assert "unknown-x" in str(exc)


class TestCodeGraphGateway:
    def setup_method(self):
        CodeGraphGateway.reset_provider()

    def teardown_method(self):
        CodeGraphGateway.reset_provider()

    def test_normalize_aliases(self):
        assert CodeGraphGateway._normalize_provider_name("codegraph") == "codegraph"
        assert CodeGraphGateway._normalize_provider_name("opensource") == "codegraph"
        assert CodeGraphGateway._normalize_provider_name("builtin") == "builtin"
        assert CodeGraphGateway._normalize_provider_name("neo4j") == "builtin"

    def test_normalize_invalid(self):
        try:
            CodeGraphGateway._normalize_provider_name("not-exist")
            assert False, "should raise"
        except ValueError as exc:
            assert "not-exist" in str(exc)

    def test_ensure_ready_skipped_when_disabled(self, monkeypatch):
        monkeypatch.setattr(gateway_mod.settings, "code_graph_enabled", False)
        CodeGraphGateway.ensure_ready()

    def test_create_search_codegraph_implements_query_apis(self, monkeypatch):
        monkeypatch.setattr(gateway_mod.settings, "code_graph_provider", "codegraph")
        monkeypatch.setattr(gateway_mod.settings, "code_graph_enabled", True)
        monkeypatch.setattr(
            "app.repo_analysis.services.codegraph.providers.codegraph.provider.ensure_codegraph_cli",
            lambda: "codegraph",
        )
        CodeGraphGateway.reset_provider()
        with CodeGraphGateway.create_search() as search:
            assert isinstance(search, CodeGraphSearchBase)
            assert hasattr(search, "query_callers_of_symbol")
            assert hasattr(search, "query_callees_of_symbol")
            assert hasattr(search, "query_dependents_of_file")


class TestProviderContracts:
    def test_builtin_create_generator_type(self, monkeypatch):
        from app.config.settings import settings as settings_obj
        monkeypatch.setattr(settings_obj, "code_graph_enabled", False)
        provider = BuiltinCodeGraphProvider()
        gen = provider.create_generator("rid", "rname", "/tmp")
        assert isinstance(gen, CodeGraphGeneratorBase)

    def test_codegraph_create_generator_type(self, monkeypatch):
        monkeypatch.setattr(
            "app.repo_analysis.services.codegraph.providers.codegraph.provider.ensure_codegraph_cli",
            lambda: "codegraph",
        )
        provider = CodeGraphCliProvider()
        gen = provider.create_generator("rid", "rname", "/tmp")
        assert isinstance(gen, CodeGraphGeneratorBase)
