from __future__ import annotations

import httpx
import pytest
import respx

from workbalancer.infrastructure.cursor_client import CursorCloudClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, test_env: None) -> CursorCloudClient:
    monkeypatch.setenv("CURSOR_API_BASE", "https://api.cursor.com")
    from workbalancer.config import get_settings

    get_settings.cache_clear()
    yield CursorCloudClient()
    get_settings.cache_clear()


@pytest.mark.asyncio
@respx.mock
async def test_launch_agent_posts_json(client: CursorCloudClient) -> None:
    route = respx.post("https://api.cursor.com/v0/agents").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "bc_1",
                "status": "CREATING",
                "target": {"url": "https://cursor.com/agents?id=bc_1"},
            },
        )
    )
    data = await client.launch_agent(
        prompt_text="hello",
        repository_url="https://github.com/o/r",
        ref="main",
        webhook_url="http://localhost/webhooks/cursor",
        webhook_secret="s" * 32,
        auto_create_pr=True,
    )
    assert data["id"] == "bc_1"
    assert route.called
    req = route.calls[0].request
    body = req.content.decode()
    assert "hello" in body
    assert "github.com/o/r" in body


@pytest.mark.asyncio
@respx.mock
async def test_get_agent(client: CursorCloudClient) -> None:
    respx.get("https://api.cursor.com/v0/agents/bc_1").mock(
        return_value=httpx.Response(200, json={"id": "bc_1", "status": "RUNNING"})
    )
    data = await client.get_agent("bc_1")
    assert data["status"] == "RUNNING"
