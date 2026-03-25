from __future__ import annotations

import json
import logging
from typing import Any

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import text

from workbalancer.application.services import Orchestrator
from workbalancer.infrastructure.db import engine
from workbalancer.domain.models import AgentWebhookPayload
from workbalancer.infrastructure.webhook_verify import verify_cursor_webhook_signature
from workbalancer.presentation.notify import send_terminal_notification
from workbalancer.presentation.web.deps import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_payload(data: dict[str, Any]) -> AgentWebhookPayload:
    src = data.get("source") or {}
    tgt = data.get("target") or {}
    return AgentWebhookPayload(
        event=str(data.get("event", "")),
        agent_id=str(data.get("id", "")),
        status=str(data.get("status", "")),
        summary=data.get("summary"),
        repository=src.get("repository"),
        ref=src.get("ref"),
        agent_url=tgt.get("url"),
        branch_name=tgt.get("branchName"),
        pr_url=tgt.get("prUrl"),
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(request: Request) -> dict[str, str]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database_unavailable") from None
    redis = getattr(request.app.state, "redis_service", None)
    if redis is not None:
        try:
            await redis.ping()
        except Exception:
            raise HTTPException(status_code=503, detail="redis_unavailable") from None
    return {"status": "ready"}


@router.post("/webhooks/cursor")
async def cursor_webhook(
    request: Request, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> Response:
    settings = request.app.state.settings
    raw = await request.body()
    sig = request.headers.get("X-Webhook-Signature")
    if not verify_cursor_webhook_signature(settings.cursor_webhook_secret, raw, sig):
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="invalid json") from e

    payload = _parse_payload(data)
    webhook_id = request.headers.get("X-Webhook-ID")

    job = await orchestrator.handle_webhook_payload(payload, webhook_id)

    bot: Bot | None = getattr(request.app.state, "bot", None)
    redis = getattr(request.app.state, "redis_service", None)
    if bot and job and payload.status in ("FINISHED", "ERROR"):
        await send_terminal_notification(redis, bot, job)

    return Response(status_code=204)
