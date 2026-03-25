from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from workbalancer.infrastructure.models_orm import Base
from workbalancer.infrastructure.repositories import SqlProjectRepository, SqlChatContextRepository


@pytest_asyncio.fixture
async def async_engine(postgres_async_url: str):
    engine = create_async_engine(postgres_async_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncSession:
    factory = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_project_and_active_chat(db_session: AsyncSession) -> None:
    projects = SqlProjectRepository(db_session)
    chats = SqlChatContextRepository(db_session)
    p = await projects.create("My", "https://github.com/o/r", "main")
    await db_session.commit()
    assert p.id >= 1
    await chats.set_active_project(42, p.id)
    await db_session.commit()
    pid = await chats.get_active_project_id(42)
    assert pid == p.id
