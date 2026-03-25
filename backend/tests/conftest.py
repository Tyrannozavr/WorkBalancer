from __future__ import annotations

import os
from typing import Any

import pytest

from workbalancer.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURSOR_WEBHOOK_SECRET", "x" * 32)
    monkeypatch.setenv("CURSOR_API_KEY", "test-api-key")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1001")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()


@pytest.fixture
def settings(test_env: None):
    return get_settings()


@pytest.fixture(scope="session")
def postgres_async_url() -> str:
    if os.environ.get("SKIP_INTEGRATION"):
        pytest.skip("SKIP_INTEGRATION set")
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    with PostgresContainer("postgres:16-alpine") as postgres:
        raw = postgres.get_connection_url()
        if "postgresql+psycopg2://" in raw:
            url = raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        else:
            url = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
        yield url
