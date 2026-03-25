from __future__ import annotations

import logging

from aiogram import Bot

from workbalancer.domain.models import AgentJob, AgentJobStatus
from workbalancer.infrastructure.redis_client import RedisService

logger = logging.getLogger(__name__)


def format_job_message(job: AgentJob) -> str:
    lines = [f"Статус агента: {job.status.value}"]
    if job.summary:
        lines.append(f"\nИтог:\n{job.summary[:3500]}")
    if job.agent_url:
        lines.append(f"\nАгент: {job.agent_url}")
    if job.pr_url:
        lines.append(f"\nPR: {job.pr_url}")
    if job.error_message:
        lines.append(f"\nОшибка: {job.error_message[:500]}")
    return "\n".join(lines)


async def send_terminal_notification(
    redis: RedisService | None,
    bot: Bot,
    job: AgentJob,
) -> None:
    if job.status not in (AgentJobStatus.FINISHED, AgentJobStatus.ERROR):
        return
    if not job.cursor_agent_id:
        return
    can_send = True
    if redis is not None:
        can_send = await redis.try_notify_terminal_once(job.cursor_agent_id)
    if not can_send:
        return
    try:
        await bot.send_message(job.telegram_chat_id, format_job_message(job))
    except Exception:
        logger.exception("Failed to send Telegram terminal notification")
