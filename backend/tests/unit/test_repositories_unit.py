from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.engine import Result

from workbalancer.infrastructure.models_orm import AgentJobORM, ProjectORM
from workbalancer.infrastructure.repositories import SqlAgentJobRepository, SqlProjectRepository


@pytest.mark.asyncio
async def test_project_get_by_id_found() -> None:
    session = AsyncMock()
    row = ProjectORM(name="n", repository_url="https://github.com/o/r", ref="main")
    row.id = 7
    session.get = AsyncMock(return_value=row)
    repo = SqlProjectRepository(session)
    p = await repo.get_by_id(7)
    assert p is not None
    assert p.repository_url == "https://github.com/o/r"


@pytest.mark.asyncio
async def test_project_get_by_id_missing() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    repo = SqlProjectRepository(session)
    assert await repo.get_by_id(1) is None


@pytest.mark.asyncio
async def test_job_get_by_cursor_id() -> None:
    session = AsyncMock()
    row = AgentJobORM(
        project_id=1,
        telegram_chat_id=1,
        telegram_user_id=1,
        status="RUNNING",
        prompt_preview="p",
        cursor_agent_id="bc_1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    row.id = 3
    res = MagicMock(spec=Result)
    res.scalar_one_or_none = MagicMock(return_value=row)
    session.execute = AsyncMock(return_value=res)
    repo = SqlAgentJobRepository(session)
    job = await repo.get_by_cursor_id("bc_1")
    assert job is not None
    assert job.cursor_agent_id == "bc_1"
