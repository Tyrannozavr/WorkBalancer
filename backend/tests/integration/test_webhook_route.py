from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from workbalancer.application.services import Orchestrator
from workbalancer.domain.models import AgentJob, AgentJobStatus
from workbalancer.main import app
from workbalancer.presentation.web.deps import get_orchestrator


@pytest.fixture
def signed_body() -> tuple[bytes, str]:
    secret = "k" * 32
    raw = json.dumps(
        {
            "event": "statusChange",
            "id": "bc_1",
            "status": "FINISHED",
            "summary": "done",
            "source": {},
            "target": {},
        }
    ).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, sig


def test_webhook_rejects_bad_signature(signed_body: tuple[bytes, str]) -> None:
    raw, _ = signed_body
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        r = client.post("/webhooks/cursor", content=raw, headers={"X-Webhook-Signature": "sha256=bad"})
    assert r.status_code == 401


def test_webhook_accepts_valid_signature(monkeypatch: pytest.MonkeyPatch, signed_body: tuple[bytes, str]) -> None:
    monkeypatch.setenv("CURSOR_WEBHOOK_SECRET", "k" * 32)
    from workbalancer.config import get_settings

    get_settings.cache_clear()

    raw, sig = signed_body

    now = datetime.now(UTC)
    finished = AgentJob(
        id=1,
        cursor_agent_id="bc_1",
        project_id=1,
        telegram_chat_id=1,
        telegram_user_id=1,
        status=AgentJobStatus.FINISHED,
        prompt_preview="p",
        summary="done",
        agent_url=None,
        pr_url=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )

    mock_orch = AsyncMock(spec=Orchestrator)
    mock_orch.handle_webhook_payload = AsyncMock(return_value=finished)

    async def _override() -> Orchestrator:
        return mock_orch

    app.dependency_overrides[get_orchestrator] = _override
    try:
        with TestClient(app) as client:
            r = client.post(
                "/webhooks/cursor",
                content=raw,
                headers={"X-Webhook-Signature": sig, "X-Webhook-ID": "wh-1"},
            )
        assert r.status_code == 204
        mock_orch.handle_webhook_payload.assert_called_once()
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
