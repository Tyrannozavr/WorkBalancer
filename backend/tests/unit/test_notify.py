from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot

from workbalancer.domain.models import AgentJob, AgentJobStatus
from workbalancer.presentation.notify import format_job_message, send_terminal_notification


def _job(status: AgentJobStatus = AgentJobStatus.FINISHED, **kwargs) -> AgentJob:
    defaults = dict(
        id=1,
        cursor_agent_id="bc_x",
        project_id=1,
        telegram_chat_id=10,
        telegram_user_id=100,
        status=status,
        prompt_preview="p",
        summary=kwargs.get("summary", "Done"),
        agent_url=kwargs.get("agent_url", "https://cursor.com/agents?id=bc_x"),
        pr_url=kwargs.get("pr_url", "https://github.com/o/r/pull/1"),
        error_message=kwargs.get("error_message"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return AgentJob(**defaults)


def test_format_job_message_includes_urls() -> None:
    text = format_job_message(_job())
    assert "FINISHED" in text
    assert "Done" in text
    assert "cursor.com" in text
    assert "github.com" in text


@pytest.mark.asyncio
async def test_send_terminal_notification_skips_non_terminal() -> None:
    bot = AsyncMock(spec=Bot)
    await send_terminal_notification(None, bot, _job(status=AgentJobStatus.RUNNING))
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_terminal_notification_sends_once() -> None:
    bot = AsyncMock(spec=Bot)
    redis = AsyncMock()
    redis.try_notify_terminal_once = AsyncMock(return_value=True)
    await send_terminal_notification(redis, bot, _job())
    bot.send_message.assert_called_once()
    redis.try_notify_terminal_once.assert_called_once_with("bc_x")


@pytest.mark.asyncio
async def test_send_terminal_notification_respects_dedup() -> None:
    bot = AsyncMock(spec=Bot)
    redis = AsyncMock()
    redis.try_notify_terminal_once = AsyncMock(return_value=False)
    await send_terminal_notification(redis, bot, _job())
    bot.send_message.assert_not_called()
