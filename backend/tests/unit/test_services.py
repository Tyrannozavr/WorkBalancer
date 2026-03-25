from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from workbalancer.application.services import Orchestrator, check_telegram_allowed
from workbalancer.domain.errors import ConflictError, ForbiddenError, LimitExceededError, NotFoundError
from workbalancer.domain.models import AgentJob, AgentJobStatus, AgentWebhookPayload, Project


def _job(**kwargs) -> AgentJob:
    d = dict(
        id=1,
        cursor_agent_id="bc_1",
        project_id=1,
        telegram_chat_id=1,
        telegram_user_id=100,
        status=AgentJobStatus.RUNNING,
        prompt_preview="x",
        summary=None,
        agent_url=None,
        pr_url=None,
        error_message=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d.update(kwargs)
    return AgentJob(**d)


@pytest.fixture
def mock_session() -> AsyncMock:
    s = AsyncMock(spec=AsyncSession)
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.rollback = AsyncMock()
    return s


@pytest.fixture
def orchestrator(mock_session: AsyncMock, test_env: None) -> Orchestrator:
    projects = AsyncMock()
    chats = AsyncMock()
    jobs = AsyncMock()
    audit = AsyncMock()
    cursor = AsyncMock()
    redis = AsyncMock()
    return Orchestrator(
        projects=projects,
        chats=chats,
        jobs=jobs,
        audit=audit,
        cursor=cursor,
        redis=redis,
        session=mock_session,
    )


@pytest.mark.asyncio
async def test_register_project_conflict(orchestrator: Orchestrator) -> None:
    orchestrator.projects.get_by_url = AsyncMock(return_value=Project(id=1, name="a", repository_url="u", ref="main"))
    with pytest.raises(ConflictError):
        await orchestrator.register_project(1, "n", "https://github.com/o/r", "main")


@pytest.mark.asyncio
async def test_register_project_ok(orchestrator: Orchestrator) -> None:
    p = Project(id=2, name="n", repository_url="https://github.com/o/r2", ref="main")
    orchestrator.projects.get_by_url = AsyncMock(return_value=None)
    orchestrator.projects.create = AsyncMock(return_value=p)
    out = await orchestrator.register_project(1, "n", "https://github.com/o/r2", "main")
    assert out.id == 2
    orchestrator.session.commit.assert_called()


@pytest.mark.asyncio
async def test_set_active_not_found(orchestrator: Orchestrator) -> None:
    orchestrator.projects.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await orchestrator.set_active_project(1, 1, 99)


@pytest.mark.asyncio
async def test_launch_task_secret_too_short(monkeypatch: pytest.MonkeyPatch, orchestrator: Orchestrator) -> None:
    monkeypatch.setenv("CURSOR_WEBHOOK_SECRET", "short")
    from workbalancer.config import get_settings

    get_settings.cache_clear()
    orchestrator.projects.get_by_id = AsyncMock(return_value=Project(id=1, name="n", repository_url="u", ref="main"))
    with pytest.raises(ConflictError):
        await orchestrator.launch_task(1, 1, 1, "task")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_launch_task_parallel_limit(
    monkeypatch: pytest.MonkeyPatch, orchestrator: Orchestrator, test_env: None
) -> None:
    monkeypatch.setenv("MAX_PARALLEL_AGENTS_PER_USER", "1")
    from workbalancer.config import get_settings

    get_settings.cache_clear()
    orchestrator.projects.get_by_id = AsyncMock(return_value=Project(id=1, name="n", repository_url="u", ref="main"))
    orchestrator.jobs.count_active_for_user = AsyncMock(return_value=1)
    with pytest.raises(LimitExceededError):
        await orchestrator.launch_task(1, 1, 1, "task")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_launch_task_success(orchestrator: Orchestrator, test_env: None) -> None:
    orchestrator.projects.get_by_id = AsyncMock(
        return_value=Project(id=1, name="n", repository_url="https://github.com/o/r", ref="main")
    )
    orchestrator.jobs.count_active_for_user = AsyncMock(return_value=0)
    orchestrator.jobs.create_pending = AsyncMock(
        return_value=_job(id=5, status=AgentJobStatus.PENDING_LAUNCH, cursor_agent_id=None)
    )
    orchestrator.jobs.update_from_launch = AsyncMock()
    orchestrator.jobs.get_by_id = AsyncMock(
        return_value=_job(id=5, cursor_agent_id="bc_new", status=AgentJobStatus.CREATING, agent_url="https://a")
    )
    orchestrator.cursor.launch_agent = AsyncMock(
        return_value={"id": "bc_new", "status": "CREATING", "target": {"url": "https://a"}}
    )
    job = await orchestrator.launch_task(100, 200, 1, "do work")
    assert job.cursor_agent_id == "bc_new"
    orchestrator.cursor.launch_agent.assert_called_once()


@pytest.mark.asyncio
async def test_handle_webhook_dedup(orchestrator: Orchestrator) -> None:
    orchestrator.redis.try_acquire_webhook = AsyncMock(return_value=False)
    payload = AgentWebhookPayload(
        event="statusChange",
        agent_id="bc_1",
        status="FINISHED",
        summary="ok",
        repository=None,
        ref=None,
        agent_url=None,
        branch_name=None,
        pr_url=None,
    )
    assert await orchestrator.handle_webhook_payload(payload, "wh-1") is None


@pytest.mark.asyncio
async def test_handle_webhook_updates(orchestrator: Orchestrator) -> None:
    orchestrator.redis.try_acquire_webhook = AsyncMock(return_value=True)
    updated = _job(status=AgentJobStatus.FINISHED, summary="done")
    orchestrator.jobs.update_from_webhook = AsyncMock(return_value=updated)
    payload = AgentWebhookPayload(
        event="statusChange",
        agent_id="bc_1",
        status="FINISHED",
        summary="done",
        repository=None,
        ref=None,
        agent_url=None,
        branch_name=None,
        pr_url=None,
    )
    out = await orchestrator.handle_webhook_payload(payload, "wh-1")
    assert out is not None
    assert out.status == AgentJobStatus.FINISHED


@pytest.mark.asyncio
async def test_list_repos_cached(orchestrator: Orchestrator) -> None:
    orchestrator.redis.get_cached_repositories = AsyncMock(return_value=[{"owner": "o", "name": "n"}])
    repos = await orchestrator.list_cursor_repositories_cached()
    assert len(repos) == 1
    orchestrator.cursor.list_repositories.assert_not_called()


@pytest.mark.asyncio
async def test_list_repos_fetches_cursor(orchestrator: Orchestrator) -> None:
    orchestrator.redis.get_cached_repositories = AsyncMock(return_value=None)
    orchestrator.cursor.list_repositories = AsyncMock(return_value=[{"owner": "o"}])
    orchestrator.redis.set_cached_repositories = AsyncMock()
    repos = await orchestrator.list_cursor_repositories_cached()
    assert len(repos) == 1
    orchestrator.cursor.list_repositories.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_job_from_api(orchestrator: Orchestrator) -> None:
    orchestrator.cursor.get_agent = AsyncMock(
        return_value={"status": "FINISHED", "summary": "s", "target": {"url": "u", "prUrl": "p"}}
    )
    orchestrator.jobs.update_status_from_poll = AsyncMock()
    orchestrator.jobs.get_by_id = AsyncMock(
        side_effect=[
            _job(cursor_agent_id="bc_x", status=AgentJobStatus.RUNNING),
            _job(
                cursor_agent_id="bc_x",
                status=AgentJobStatus.FINISHED,
                summary="s",
                agent_url="u",
                pr_url="p",
            ),
        ]
    )
    job = await orchestrator.refresh_job_from_api(1)
    assert job is not None
    assert job.status == AgentJobStatus.FINISHED


@pytest.mark.asyncio
async def test_refresh_job_from_api_no_job(orchestrator: Orchestrator) -> None:
    orchestrator.jobs.get_by_id = AsyncMock(return_value=None)
    assert await orchestrator.refresh_job_from_api(1) is None


@pytest.mark.asyncio
async def test_launch_task_cursor_failed(orchestrator: Orchestrator) -> None:
    orchestrator.projects.get_by_id = AsyncMock(
        return_value=Project(id=1, name="n", repository_url="https://github.com/o/r", ref="main")
    )
    orchestrator.jobs.count_active_for_user = AsyncMock(return_value=0)
    orchestrator.jobs.create_pending = AsyncMock(
        return_value=_job(id=9, status=AgentJobStatus.PENDING_LAUNCH, cursor_agent_id=None)
    )
    orchestrator.cursor.launch_agent = AsyncMock(side_effect=RuntimeError("api down"))
    orchestrator.jobs.mark_launch_failed = AsyncMock()
    with pytest.raises(RuntimeError):
        await orchestrator.launch_task(1, 1, 1, "x")
    orchestrator.jobs.mark_launch_failed.assert_called_once()


def test_check_telegram_allowed(test_env: None) -> None:
    check_telegram_allowed(1001)


def test_check_telegram_allowed_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1")
    from workbalancer.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ForbiddenError):
        check_telegram_allowed(999)
    get_settings.cache_clear()
