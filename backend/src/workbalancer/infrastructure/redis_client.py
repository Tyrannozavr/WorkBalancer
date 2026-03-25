from __future__ import annotations

import json

import redis.asyncio as redis

from workbalancer.application.ports import RedisPort
from workbalancer.config import get_settings


class RedisService(RedisPort):
    def __init__(self) -> None:
        self._settings = get_settings()
        self._r: redis.Redis | None = None

    async def _conn(self) -> redis.Redis:
        if self._r is None:
            self._r = redis.from_url(self._settings.redis_url, decode_responses=True)
        return self._r

    async def try_acquire_webhook(self, webhook_id: str | None, agent_id: str, status: str) -> bool:
        key_id = webhook_id.strip() if webhook_id else f"{agent_id}:{status}"
        r = await self._conn()
        key = f"wb:wh:{key_id}"
        ok = await r.set(key, "1", nx=True, ex=86400)
        return bool(ok)

    async def set_pending_task(self, chat_id: int, project_id: int, prompt: str) -> None:
        r = await self._conn()
        payload = json.dumps({"project_id": project_id, "prompt": prompt})
        await r.set(f"wb:pending:{chat_id}", payload, ex=3600)

    async def get_pending_task(self, chat_id: int) -> tuple[int, str] | None:
        r = await self._conn()
        raw = await r.get(f"wb:pending:{chat_id}")
        if not raw:
            return None
        data = json.loads(raw)
        return int(data["project_id"]), str(data["prompt"])

    async def clear_pending_task(self, chat_id: int) -> None:
        r = await self._conn()
        await r.delete(f"wb:pending:{chat_id}")

    async def get_cached_repositories(self) -> list[dict] | None:
        r = await self._conn()
        raw = await r.get("wb:cursor:repos")
        if not raw:
            return None
        return json.loads(raw)

    async def set_cached_repositories(self, repos: list[dict], ttl_seconds: int) -> None:
        r = await self._conn()
        await r.set("wb:cursor:repos", json.dumps(repos), ex=ttl_seconds)

    async def try_notify_terminal_once(self, cursor_agent_id: str) -> bool:
        if not cursor_agent_id:
            return False
        r = await self._conn()
        key = f"wb:notify:{cursor_agent_id}"
        ok = await r.set(key, "1", nx=True, ex=86400 * 7)
        return bool(ok)

    async def set_last_agent_for_chat(self, chat_id: int, cursor_agent_id: str) -> None:
        r = await self._conn()
        await r.set(f"wb:last_agent:{chat_id}", cursor_agent_id, ex=86400 * 30)

    async def get_last_agent_for_chat(self, chat_id: int) -> str | None:
        r = await self._conn()
        v = await r.get(f"wb:last_agent:{chat_id}")
        return str(v) if v else None

    async def ping(self) -> None:
        r = await self._conn()
        await r.ping()
