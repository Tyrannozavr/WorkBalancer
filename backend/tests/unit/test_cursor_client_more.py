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
async def test_followup(client: CursorCloudClient) -> None:
    respx.post("https://api.cursor.com/v0/agents/bc_1/followup").mock(
        return_value=httpx.Response(200, json={"id": "bc_1"})
    )
    await client.add_followup("bc_1", "more")


@pytest.mark.asyncio
@respx.mock
async def test_stop_agent(client: CursorCloudClient) -> None:
    respx.post("https://api.cursor.com/v0/agents/bc_1/stop").mock(return_value=httpx.Response(200, json={"id": "bc_1"}))
    await client.stop_agent("bc_1")


@pytest.mark.asyncio
@respx.mock
async def test_list_repositories(client: CursorCloudClient) -> None:
    respx.get("https://api.cursor.com/v0/repositories").mock(
        return_value=httpx.Response(
            200,
            json={"repositories": [{"owner": "a", "name": "b", "repository": "https://github.com/a/b"}]},
        )
    )
    repos = await client.list_repositories()
    assert len(repos) == 1
