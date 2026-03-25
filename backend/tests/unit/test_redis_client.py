from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from workbalancer.infrastructure.redis_client import RedisService


@pytest.fixture
def redis_svc(monkeypatch: pytest.MonkeyPatch, test_env: None) -> RedisService:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from workbalancer.config import get_settings

    get_settings.cache_clear()
    svc = RedisService()
    svc._r = None
    return svc


@pytest.mark.asyncio
async def test_try_acquire_webhook_first_wins(redis_svc: RedisService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AsyncMock()
    fake.set = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "workbalancer.infrastructure.redis_client.redis.from_url",
        lambda *a, **k: fake,
    )
    redis_svc._r = None
    assert await redis_svc.try_acquire_webhook("wh1", "a1", "FINISHED") is True
    fake.set.assert_called_once()


@pytest.mark.asyncio
async def test_pending_task_roundtrip(redis_svc: RedisService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AsyncMock()
    fake.set = AsyncMock()
    fake.get = AsyncMock(return_value='{"project_id": 3, "prompt": "hi"}')
    fake.delete = AsyncMock()
    monkeypatch.setattr(
        "workbalancer.infrastructure.redis_client.redis.from_url",
        lambda *a, **k: fake,
    )
    redis_svc._r = None
    await redis_svc.set_pending_task(10, 3, "hi")
    assert await redis_svc.get_pending_task(10) == (3, "hi")
    await redis_svc.clear_pending_task(10)


@pytest.mark.asyncio
async def test_repos_cache(redis_svc: RedisService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AsyncMock()
    fake.get = AsyncMock(return_value=None)
    fake.set = AsyncMock()
    monkeypatch.setattr(
        "workbalancer.infrastructure.redis_client.redis.from_url",
        lambda *a, **k: fake,
    )
    redis_svc._r = None
    assert await redis_svc.get_cached_repositories() is None
    await redis_svc.set_cached_repositories([{"owner": "o"}], 60)
    fake.set.assert_called()


@pytest.mark.asyncio
async def test_ping(redis_svc: RedisService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AsyncMock()
    fake.ping = AsyncMock()
    monkeypatch.setattr(
        "workbalancer.infrastructure.redis_client.redis.from_url",
        lambda *a, **k: fake,
    )
    redis_svc._r = None
    await redis_svc.ping()
    fake.ping.assert_called_once()


@pytest.mark.asyncio
async def test_notify_terminal_once(redis_svc: RedisService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AsyncMock()
    fake.set = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "workbalancer.infrastructure.redis_client.redis.from_url",
        lambda *a, **k: fake,
    )
    redis_svc._r = None
    assert await redis_svc.try_notify_terminal_once("bc_1") is True
