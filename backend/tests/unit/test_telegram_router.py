from unittest.mock import AsyncMock

from workbalancer.config import Settings
from workbalancer.infrastructure.cursor_client import CursorCloudClient
from workbalancer.infrastructure.redis_client import RedisService
from workbalancer.presentation.telegram.bot import build_router


def test_build_router_creates_handlers(test_env: None) -> None:
    settings = Settings()
    r = build_router(settings, AsyncMock(spec=CursorCloudClient), AsyncMock(spec=RedisService))
    assert r.message.handlers
    assert r.callback_query.handlers
