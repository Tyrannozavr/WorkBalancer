from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from workbalancer.application.ports import (
    AgentJobRepositoryPort,
    AuditRepositoryPort,
    ChatContextRepositoryPort,
    ProjectRepositoryPort,
)
from workbalancer.domain.models import AgentJob, AgentJobStatus, AgentWebhookPayload, Project
from workbalancer.infrastructure.models_orm import AgentJobORM, AuditLogORM, ProjectORM, TelegramChatContextORM


def _map_status(s: str) -> AgentJobStatus:
    try:
        return AgentJobStatus(s)
    except ValueError:
        return AgentJobStatus.UNKNOWN


def _project_from_orm(row: ProjectORM) -> Project:
    return Project(
        id=row.id,
        name=row.name,
        repository_url=row.repository_url,
        ref=row.ref,
    )


def _job_from_orm(row: AgentJobORM) -> AgentJob:
    return AgentJob(
        id=row.id,
        cursor_agent_id=row.cursor_agent_id,
        project_id=row.project_id,
        telegram_chat_id=row.telegram_chat_id,
        telegram_user_id=row.telegram_user_id,
        status=_map_status(row.status),
        prompt_preview=row.prompt_preview,
        summary=row.summary,
        agent_url=row.agent_url,
        pr_url=row.pr_url,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlProjectRepository(ProjectRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_projects(self) -> list[Project]:
        res = await self._s.execute(select(ProjectORM).order_by(ProjectORM.id))
        return [_project_from_orm(r) for r in res.scalars().all()]

    async def get_by_id(self, project_id: int) -> Project | None:
        row = await self._s.get(ProjectORM, project_id)
        return _project_from_orm(row) if row else None

    async def get_by_url(self, repository_url: str) -> Project | None:
        res = await self._s.execute(select(ProjectORM).where(ProjectORM.repository_url == repository_url))
        row = res.scalar_one_or_none()
        return _project_from_orm(row) if row else None

    async def create(self, name: str, repository_url: str, ref: str) -> Project:
        row = ProjectORM(name=name, repository_url=repository_url, ref=ref)
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _project_from_orm(row)


class SqlChatContextRepository(ChatContextRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_active_project_id(self, chat_id: int) -> int | None:
        row = await self._s.get(TelegramChatContextORM, chat_id)
        return row.active_project_id if row else None

    async def set_active_project(self, chat_id: int, project_id: int | None) -> None:
        row = await self._s.get(TelegramChatContextORM, chat_id)
        if row is None:
            self._s.add(TelegramChatContextORM(chat_id=chat_id, active_project_id=project_id))
        else:
            row.active_project_id = project_id
        await self._s.flush()


class SqlAgentJobRepository(AgentJobRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_pending(
        self,
        project_id: int,
        telegram_chat_id: int,
        telegram_user_id: int,
        prompt_preview: str,
    ) -> AgentJob:
        row = AgentJobORM(
            project_id=project_id,
            telegram_chat_id=telegram_chat_id,
            telegram_user_id=telegram_user_id,
            status=AgentJobStatus.PENDING_LAUNCH.value,
            prompt_preview=prompt_preview[:2000],
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _job_from_orm(row)

    async def update_from_launch(self, job_id: int, cursor_agent_id: str, status: str, agent_url: str | None) -> None:
        await self._s.execute(
            update(AgentJobORM)
            .where(AgentJobORM.id == job_id)
            .values(
                cursor_agent_id=cursor_agent_id,
                status=status,
                agent_url=agent_url,
                updated_at=datetime.now(UTC),
            )
        )

    async def update_from_webhook(
        self, cursor_agent_id: str, payload: AgentWebhookPayload, webhook_delivery_id: str | None
    ) -> AgentJob | None:
        res = await self._s.execute(select(AgentJobORM).where(AgentJobORM.cursor_agent_id == cursor_agent_id))
        row = res.scalar_one_or_none()
        if row is None:
            return None
        row.status = payload.status
        row.summary = payload.summary
        row.agent_url = payload.agent_url or row.agent_url
        row.pr_url = payload.pr_url or row.pr_url
        row.webhook_delivery_id = webhook_delivery_id
        row.updated_at = datetime.now(UTC)
        await self._s.flush()
        await self._s.refresh(row)
        return _job_from_orm(row)

    async def get_by_cursor_id(self, cursor_agent_id: str) -> AgentJob | None:
        res = await self._s.execute(select(AgentJobORM).where(AgentJobORM.cursor_agent_id == cursor_agent_id))
        row = res.scalar_one_or_none()
        return _job_from_orm(row) if row else None

    async def get_by_id(self, job_id: int) -> AgentJob | None:
        row = await self._s.get(AgentJobORM, job_id)
        return _job_from_orm(row) if row else None

    async def count_active_for_user(self, telegram_user_id: int) -> int:
        res = await self._s.execute(
            select(func.count())
            .select_from(AgentJobORM)
            .where(
                AgentJobORM.telegram_user_id == telegram_user_id,
                AgentJobORM.status.in_([AgentJobStatus.CREATING.value, AgentJobStatus.RUNNING.value]),
            )
        )
        return int(res.scalar_one() or 0)

    async def list_stale_running(self, older_than_seconds: int) -> list[AgentJob]:
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        res = await self._s.execute(
            select(AgentJobORM).where(
                AgentJobORM.status.in_([AgentJobStatus.CREATING.value, AgentJobStatus.RUNNING.value]),
                AgentJobORM.created_at < cutoff,
                AgentJobORM.cursor_agent_id.isnot(None),
            )
        )
        return [_job_from_orm(r) for r in res.scalars().all()]

    async def mark_launch_failed(self, job_id: int, error_message: str) -> None:
        await self._s.execute(
            update(AgentJobORM)
            .where(AgentJobORM.id == job_id)
            .values(
                status=AgentJobStatus.ERROR.value,
                error_message=error_message[:4000],
                updated_at=datetime.now(UTC),
            )
        )

    async def update_status_from_poll(self, job_id: int, status: str, summary: str | None, agent_url: str | None, pr_url: str | None) -> None:
        await self._s.execute(
            update(AgentJobORM)
            .where(AgentJobORM.id == job_id)
            .values(
                status=status,
                summary=summary,
                agent_url=agent_url,
                pr_url=pr_url,
                updated_at=datetime.now(UTC),
            )
        )

    async def list_recent_for_chat(self, chat_id: int, limit: int) -> list[AgentJob]:
        res = await self._s.execute(
            select(AgentJobORM)
            .where(AgentJobORM.telegram_chat_id == chat_id)
            .order_by(AgentJobORM.id.desc())
            .limit(limit)
        )
        return [_job_from_orm(r) for r in res.scalars().all()]

    async def list_active_for_chat(self, chat_id: int) -> list[AgentJob]:
        res = await self._s.execute(
            select(AgentJobORM)
            .where(
                AgentJobORM.telegram_chat_id == chat_id,
                AgentJobORM.status.in_(
                    [
                        AgentJobStatus.PENDING_LAUNCH.value,
                        AgentJobStatus.CREATING.value,
                        AgentJobStatus.RUNNING.value,
                    ]
                ),
            )
            .order_by(AgentJobORM.id.desc())
        )
        return [_job_from_orm(r) for r in res.scalars().all()]

    async def update_status_by_cursor_id(self, cursor_agent_id: str, status: str) -> None:
        await self._s.execute(
            update(AgentJobORM)
            .where(AgentJobORM.cursor_agent_id == cursor_agent_id)
            .values(status=status, updated_at=datetime.now(UTC))
        )


class SqlAuditRepository(AuditRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def log(self, telegram_user_id: int, action: str, details: dict) -> None:
        self._s.add(AuditLogORM(telegram_user_id=telegram_user_id, action=action, details=details))
        await self._s.flush()
