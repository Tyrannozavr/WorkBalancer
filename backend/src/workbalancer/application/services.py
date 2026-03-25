from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from workbalancer.application.ports import (
    AgentJobRepositoryPort,
    AuditRepositoryPort,
    ChatContextRepositoryPort,
    CursorCloudPort,
    ProjectRepositoryPort,
    RedisPort,
)
from workbalancer.config import get_settings
from workbalancer.domain.errors import ConflictError, ForbiddenError, LimitExceededError, NotFoundError
from workbalancer.domain.models import AgentJob, AgentJobStatus, AgentWebhookPayload, Project

logger = logging.getLogger(__name__)


def _preview(text: str, n: int = 500) -> str:
    t = text.strip()
    return t if len(t) <= n else t[: n - 1] + "…"


@dataclass(slots=True)
class Orchestrator:
    projects: ProjectRepositoryPort
    chats: ChatContextRepositoryPort
    jobs: AgentJobRepositoryPort
    audit: AuditRepositoryPort
    cursor: CursorCloudPort
    redis: RedisPort
    session: AsyncSession

    async def register_project(self, telegram_user_id: int, name: str, repository_url: str, ref: str) -> Project:
        existing = await self.projects.get_by_url(repository_url)
        if existing:
            raise ConflictError("Project with this repository URL already exists")
        p = await self.projects.create(name=name, repository_url=repository_url.rstrip("/"), ref=ref or "main")
        await self.audit.log(
            telegram_user_id,
            "register_project",
            {"project_id": p.id, "repository_url": repository_url, "ref": ref},
        )
        await self.session.commit()
        return p

    async def set_active_project(self, telegram_user_id: int, chat_id: int, project_id: int) -> Project:
        p = await self.projects.get_by_id(project_id)
        if p is None:
            raise NotFoundError("Project not found")
        await self.chats.set_active_project(chat_id, project_id)
        await self.audit.log(
            telegram_user_id,
            "set_active_project",
            {"chat_id": chat_id, "project_id": project_id},
        )
        await self.session.commit()
        return p

    async def get_active_project(self, chat_id: int) -> Project | None:
        pid = await self.chats.get_active_project_id(chat_id)
        if pid is None:
            return None
        return await self.projects.get_by_id(pid)

    async def prepare_task(self, chat_id: int, project_id: int, prompt: str) -> None:
        await self.redis.set_pending_task(chat_id, project_id, prompt)

    async def launch_task(
        self,
        telegram_user_id: int,
        chat_id: int,
        project_id: int,
        prompt: str,
    ) -> AgentJob:
        settings = get_settings()
        if len(settings.cursor_webhook_secret) < 32:
            raise ConflictError("CURSOR_WEBHOOK_SECRET must be at least 32 characters")

        p = await self.projects.get_by_id(project_id)
        if p is None:
            raise NotFoundError("Project not found")

        n_active = await self.jobs.count_active_for_user(telegram_user_id)
        if n_active >= settings.max_parallel_agents_per_user:
            raise LimitExceededError(
                f"Too many running agents ({n_active}). Max: {settings.max_parallel_agents_per_user}"
            )

        preview = _preview(prompt)
        job = await self.jobs.create_pending(
            project_id=p.id,
            telegram_chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            prompt_preview=preview,
        )
        await self.session.flush()

        webhook_url = settings.public_base_url.rstrip("/") + "/webhooks/cursor"
        enriched_prompt = (
            f"Repository: {p.repository_url}\n"
            f"Base ref: {p.ref}\n\n"
            f"Task:\n{prompt}"
        )

        try:
            data = await self.cursor.launch_agent(
                prompt_text=enriched_prompt,
                repository_url=p.repository_url,
                ref=p.ref,
                webhook_url=webhook_url,
                webhook_secret=settings.cursor_webhook_secret,
                auto_create_pr=True,
            )
        except Exception as e:
            logger.exception("Cursor launch failed")
            await self.jobs.mark_launch_failed(job.id, str(e))
            await self.audit.log(
                telegram_user_id,
                "launch_failed",
                {"job_id": job.id, "error": str(e), "preview": preview},
            )
            await self.session.commit()
            raise

        agent_id = data.get("id", "")
        status = data.get("status", "CREATING")
        target = data.get("target") or {}
        agent_url = target.get("url")

        await self.jobs.update_from_launch(job.id, agent_id, status, agent_url)
        if agent_id:
            await self.redis.set_last_agent_for_chat(chat_id, agent_id)
        await self.audit.log(
            telegram_user_id,
            "launch_agent",
            {"job_id": job.id, "cursor_agent_id": agent_id, "preview": preview},
        )
        await self.session.commit()

        updated = await self.jobs.get_by_id(job.id)
        assert updated is not None
        return updated

    async def handle_webhook_payload(
        self,
        payload: AgentWebhookPayload,
        webhook_delivery_id: str | None,
    ) -> AgentJob | None:
        if not await self.redis.try_acquire_webhook(webhook_delivery_id, payload.agent_id, payload.status):
            return None

        job = await self.jobs.update_from_webhook(payload.agent_id, payload, webhook_delivery_id)
        if job is None:
            logger.warning("Webhook for unknown agent %s", payload.agent_id)
            await self.session.commit()
            return None

        await self.audit.log(
            job.telegram_user_id,
            "webhook_status",
            {
                "cursor_agent_id": payload.agent_id,
                "status": payload.status,
                "summary": _preview(payload.summary or "", 200),
            },
        )
        await self.session.commit()
        return job

    async def refresh_job_from_api(self, job_id: int) -> AgentJob | None:
        job = await self.jobs.get_by_id(job_id)
        if job is None or not job.cursor_agent_id:
            return None
        try:
            data = await self.cursor.get_agent(job.cursor_agent_id)
        except Exception as e:
            logger.warning("Poll agent failed: %s", e)
            return None
        status = data.get("status", job.status.value)
        target = data.get("target") or {}
        summary = data.get("summary")
        await self.jobs.update_status_from_poll(
            job_id,
            status,
            summary,
            target.get("url"),
            target.get("prUrl"),
        )
        await self.session.commit()
        refreshed = await self.jobs.get_by_id(job_id)
        return refreshed

    async def list_cursor_repositories_cached(self) -> list[dict]:
        cached = await self.redis.get_cached_repositories()
        if cached is not None:
            return cached
        repos = await self.cursor.list_repositories()
        await self.redis.set_cached_repositories(repos, ttl_seconds=3600)
        return repos

    async def _resolve_cursor_agent_for_chat(self, chat_id: int) -> str | None:
        aid = await self.redis.get_last_agent_for_chat(chat_id)
        if aid:
            return aid
        active = await self.jobs.list_active_for_chat(chat_id)
        for j in active:
            if j.cursor_agent_id:
                return j.cursor_agent_id
        recent = await self.jobs.list_recent_for_chat(chat_id, 10)
        for j in recent:
            if j.cursor_agent_id:
                return j.cursor_agent_id
        return None

    async def followup_agent(self, telegram_user_id: int, chat_id: int, prompt: str) -> str:
        agent_id = await self._resolve_cursor_agent_for_chat(chat_id)
        if not agent_id:
            raise NotFoundError("Нет агента для follow-up (сначала /task или укажите job через /status).")
        preview = _preview(prompt)
        try:
            await self.cursor.add_followup(agent_id, prompt)
        except Exception as e:
            logger.exception("followup failed")
            await self.audit.log(
                telegram_user_id,
                "followup_failed",
                {"cursor_agent_id": agent_id, "error": str(e), "preview": preview},
            )
            await self.session.commit()
            raise
        await self.audit.log(
            telegram_user_id,
            "followup",
            {"cursor_agent_id": agent_id, "preview": preview},
        )
        await self.session.commit()
        return agent_id

    async def _get_job_for_stop(
        self, telegram_user_id: int, chat_id: int, job_id: int | None
    ) -> AgentJob:
        if job_id is not None:
            job = await self.jobs.get_by_id(job_id)
            if job is None:
                raise NotFoundError("Job не найден")
            if job.telegram_chat_id != chat_id or job.telegram_user_id != telegram_user_id:
                raise ForbiddenError("Нет доступа к этому job")
            if not job.cursor_agent_id:
                raise NotFoundError("У job нет cursor_agent_id")
            return job
        active = await self.jobs.list_active_for_chat(chat_id)
        for j in active:
            if j.telegram_user_id == telegram_user_id and j.cursor_agent_id:
                return j
        aid = await self._resolve_cursor_agent_for_chat(chat_id)
        if not aid:
            raise NotFoundError("Нет активного агента для остановки")
        job = await self.jobs.get_by_cursor_id(aid)
        if job is None:
            raise NotFoundError("Запись job не найдена")
        if job.telegram_user_id != telegram_user_id or job.telegram_chat_id != chat_id:
            raise ForbiddenError("Нет доступа")
        return job

    async def stop_agent_job(self, telegram_user_id: int, chat_id: int, job_id: int | None) -> AgentJob:
        job = await self._get_job_for_stop(telegram_user_id, chat_id, job_id)
        assert job.cursor_agent_id
        try:
            await self.cursor.stop_agent(job.cursor_agent_id)
        except Exception as e:
            logger.exception("stop_agent failed")
            await self.audit.log(
                telegram_user_id,
                "stop_failed",
                {"job_id": job.id, "cursor_agent_id": job.cursor_agent_id, "error": str(e)},
            )
            await self.session.commit()
            raise
        await self.jobs.update_status_by_cursor_id(job.cursor_agent_id, AgentJobStatus.STOPPED.value)
        await self.audit.log(
            telegram_user_id,
            "stop_agent",
            {"job_id": job.id, "cursor_agent_id": job.cursor_agent_id},
        )
        await self.session.commit()
        out = await self.jobs.get_by_id(job.id)
        assert out is not None
        return out

    async def list_jobs_for_chat(self, chat_id: int, telegram_user_id: int, limit: int = 15) -> list[AgentJob]:
        jobs = await self.jobs.list_recent_for_chat(chat_id, limit)
        return [j for j in jobs if j.telegram_user_id == telegram_user_id]


def check_telegram_allowed(user_id: int) -> None:
    settings = get_settings()
    allowed = settings.allowed_telegram_user_ids_set
    if not allowed:
        raise ForbiddenError("TELEGRAM_ALLOWED_USER_IDS is empty — configure allowlist")
    if user_id not in allowed:
        raise ForbiddenError("User not allowed")
