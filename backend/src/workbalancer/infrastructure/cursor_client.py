from __future__ import annotations

import httpx

from workbalancer.application.ports import CursorCloudPort
from workbalancer.config import get_settings


class CursorCloudClient(CursorCloudPort):
    def __init__(self) -> None:
        self._settings = get_settings()
        self._base = self._settings.cursor_api_base.rstrip("/")
        self._auth = (self._settings.cursor_api_key, "")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, auth=self._auth, timeout=120.0)

    async def launch_agent(
        self,
        prompt_text: str,
        repository_url: str,
        ref: str,
        webhook_url: str,
        webhook_secret: str,
        auto_create_pr: bool,
    ) -> dict:
        body: dict = {
            "prompt": {"text": prompt_text},
            "source": {"repository": repository_url, "ref": ref},
            "target": {"autoCreatePr": auto_create_pr},
            "webhook": {"url": webhook_url, "secret": webhook_secret},
        }
        async with self._client() as c:
            r = await c.post("/v0/agents", json=body)
            r.raise_for_status()
            return r.json()

    async def get_agent(self, agent_id: str) -> dict:
        async with self._client() as c:
            r = await c.get(f"/v0/agents/{agent_id}")
            r.raise_for_status()
            return r.json()

    async def add_followup(self, agent_id: str, prompt_text: str) -> dict:
        body = {"prompt": {"text": prompt_text}}
        async with self._client() as c:
            r = await c.post(f"/v0/agents/{agent_id}/followup", json=body)
            r.raise_for_status()
            return r.json()

    async def stop_agent(self, agent_id: str) -> None:
        async with self._client() as c:
            r = await c.post(f"/v0/agents/{agent_id}/stop")
            r.raise_for_status()

    async def list_repositories(self) -> list[dict]:
        async with self._client() as c:
            r = await c.get("/v0/repositories")
            r.raise_for_status()
            data = r.json()
            return list(data.get("repositories", []))
