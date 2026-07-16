"""场景套件：共享会话清理。"""
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.framework.session_support import ScenarioSession


@pytest.fixture(scope="session", autouse=True)
def _accuracy_summary():
    AccuracyMetrics.reset()
    yield
    AccuracyMetrics.print_summary()


@pytest.fixture(scope="session", autouse=True)
def _shutdown_scenario_session():
    yield
    try:
        ScenarioSession().run_async(ScenarioSession.shutdown_runtime())
    except Exception:
        pass
