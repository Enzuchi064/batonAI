import pytest
from fastapi.testclient import TestClient

from baton.api import create_app
from baton.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        db_path=tmp_path / "baton.db",
        fake_autostart=True,
        fake_agents=1,
        approval_timeout_s=10.0,
        dev_mode=True,
        opencode_enabled=False,
        local_agents_enabled=False,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
