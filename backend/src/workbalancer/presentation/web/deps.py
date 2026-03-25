from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from workbalancer.application.services import Orchestrator
from workbalancer.infrastructure.cursor_client import CursorCloudClient
from workbalancer.infrastructure.db import get_session
from workbalancer.infrastructure.redis_client import RedisService
from workbalancer.infrastructure.repositories import (
    SqlAgentJobRepository,
    SqlAuditRepository,
    SqlChatContextRepository,
    SqlProjectRepository,
)


def get_cursor(request: Request) -> CursorCloudClient:
    return request.app.state.cursor_client


def get_redis(request: Request) -> RedisService:
    return request.app.state.redis_service


async def get_orchestrator(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: Annotated[CursorCloudClient, Depends(get_cursor)],
    redis: Annotated[RedisService, Depends(get_redis)],
) -> Orchestrator:
    return Orchestrator(
        projects=SqlProjectRepository(session),
        chats=SqlChatContextRepository(session),
        jobs=SqlAgentJobRepository(session),
        audit=SqlAuditRepository(session),
        cursor=cursor,
        redis=redis,
        session=session,
    )
