from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from workbalancer.application.services import Orchestrator
from workbalancer.config import get_settings
from workbalancer.infrastructure.cursor_client import CursorCloudClient
from workbalancer.infrastructure.db import SessionLocal
from workbalancer.infrastructure.redis_client import RedisService
from workbalancer.infrastructure.repositories import (
    SqlAgentJobRepository,
    SqlAuditRepository,
    SqlChatContextRepository,
    SqlProjectRepository,
)
from workbalancer.presentation.notify import send_terminal_notification
from workbalancer.presentation.telegram.bot import build_router as build_tg_router
from workbalancer.presentation.web.routes import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("workbalancer")


def _make_orch(session, cursor: CursorCloudClient, redis: RedisService) -> Orchestrator:
    return Orchestrator(
        projects=SqlProjectRepository(session),
        chats=SqlChatContextRepository(session),
        jobs=SqlAgentJobRepository(session),
        audit=SqlAuditRepository(session),
        cursor=cursor,
        redis=redis,
        session=session,
    )


async def poll_stale_loop(bot: Bot, redis: RedisService, cursor: CursorCloudClient) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            async with SessionLocal() as session:
                orch = _make_orch(session, cursor, redis)
                stale = await orch.jobs.list_stale_running(older_than_seconds=45)
                job_ids = [j.id for j in stale]
            for jid in job_ids:
                async with SessionLocal() as session:
                    orch = _make_orch(session, cursor, redis)
                    job = await orch.refresh_job_from_api(jid)
                    if job:
                        await send_terminal_notification(redis, bot, job)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("poll_stale_loop error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    redis = RedisService()
    cursor = CursorCloudClient()
    app.state.settings = settings
    app.state.redis_service = redis
    app.state.cursor_client = cursor

    poll_task: asyncio.Task | None = None
    bot_task: asyncio.Task | None = None

    if settings.telegram_bot_token:
        bot = Bot(settings.telegram_bot_token)
        app.state.bot = bot
        dp = Dispatcher()
        dp.include_router(build_tg_router(settings, cursor, redis))
        poll_task = asyncio.create_task(poll_stale_loop(bot, redis, cursor))
        bot_task = asyncio.create_task(dp.start_polling(bot))
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        app.state.bot = None

    yield

    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    if poll_task:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="WorkBalancer", lifespan=lifespan)
app.include_router(api_router)


def main() -> None:
    uvicorn.run("workbalancer.main:app", host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
