from __future__ import annotations

import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from workbalancer.application.services import Orchestrator, check_telegram_allowed
from workbalancer.config import Settings
from workbalancer.domain.errors import ConflictError, ForbiddenError, LimitExceededError, NotFoundError
from workbalancer.infrastructure.cursor_client import CursorCloudClient
from workbalancer.infrastructure.db import SessionLocal
from workbalancer.infrastructure.redis_client import RedisService
from workbalancer.infrastructure.repositories import (
    SqlAgentJobRepository,
    SqlAuditRepository,
    SqlChatContextRepository,
    SqlProjectRepository,
)

logger = logging.getLogger(__name__)


def _orch(session, cursor: CursorCloudClient, redis: RedisService) -> Orchestrator:
    return Orchestrator(
        projects=SqlProjectRepository(session),
        chats=SqlChatContextRepository(session),
        jobs=SqlAgentJobRepository(session),
        audit=SqlAuditRepository(session),
        cursor=cursor,
        redis=redis,
        session=session,
    )


def _truncate(text: str, max_len: int = 3500) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _deny_reason(exc: Exception) -> str:
    if isinstance(exc, ForbiddenError):
        return str(exc)
    if isinstance(exc, NotFoundError):
        return str(exc)
    if isinstance(exc, ConflictError):
        return str(exc)
    if isinstance(exc, LimitExceededError):
        return str(exc)
    return "Ошибка выполнения"


def build_router(settings: Settings, cursor: CursorCloudClient, redis: RedisService) -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if not message.from_user:
            return
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        await message.answer(
            "Команды:\n"
            "/projects — список проектов\n"
            "/add <repo_url> <ref> [имя] — добавить проект\n"
            "/use <id> — активный проект для чата\n"
            "/task <текст> — запустить агента Cursor\n"
            "/followup или /fu <текст> — уточнение к последнему агенту\n"
            "/stop [job_id] — остановить агента (без id — последний активный)\n"
            "/status — последние задачи в этом чате\n"
            "/repos — репозитории Cursor (кэш)\n"
            "/cancel — отменить подтверждение задачи"
        )

    @router.message(Command("projects"))
    async def cmd_projects(message: Message) -> None:
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            projects = await orch.projects.list_projects()
            await session.commit()
        if not projects:
            await message.answer("Проектов пока нет. /add …")
            return
        lines = [f"{p.id}: {p.name} — {p.repository_url} @ {p.ref}" for p in projects]
        await message.answer("\n".join(lines))

    @router.message(Command("add"))
    async def cmd_add(message: Message) -> None:
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Использование: /add <repo_url> [ref] [имя]\nПример: /add https://github.com/org/repo main MyApp")
            return
        url = parts[1]
        ref = parts[2] if len(parts) > 2 else "main"
        name = " ".join(parts[3:]) if len(parts) > 3 else url.split("/")[-1].replace(".git", "") or "project"
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            try:
                p = await orch.register_project(message.from_user.id, name, url, ref)
            except ConflictError as e:
                await session.rollback()
                await message.answer(_deny_reason(e))
                return
            await session.commit()
        await message.answer(f"Проект добавлен: {p.id} — {p.name}")

    @router.message(Command("use"))
    async def cmd_use(message: Message) -> None:
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Использование: /use <id>")
            return
        try:
            pid = int(parts[1])
        except ValueError:
            await message.answer("id должен быть числом")
            return
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            try:
                p = await orch.set_active_project(message.from_user.id, message.chat.id, pid)
            except NotFoundError as e:
                await session.rollback()
                await message.answer(_deny_reason(e))
                return
            await session.commit()
        await message.answer(f"Активный проект: {p.id} — {p.repository_url} @ {p.ref}")

    async def orch_prepare_and_confirm(message: Message, redis_svc: RedisService, project_id: int, prompt: str) -> None:
        await redis_svc.set_pending_task(message.chat.id, project_id, prompt)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Запустить", callback_data="wb_confirm"),
                    InlineKeyboardButton(text="Отмена", callback_data="wb_cancel"),
                ]
            ]
        )
        preview = prompt if len(prompt) < 800 else prompt[:799] + "…"
        await message.answer(f"Подтвердите запуск агента для проекта #{project_id}:\n\n{preview}", reply_markup=kb)

    async def _launch_and_reply(
        message: Message,
        *,
        user_id: int,
        chat_id: int,
        project_id: int,
        prompt: str,
    ) -> None:
        await message.answer("Запускаю агента Cursor…")
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            try:
                job = await orch.launch_task(user_id, chat_id, project_id, prompt)
            except (NotFoundError, ConflictError, LimitExceededError) as e:
                await session.rollback()
                await message.answer(_deny_reason(e))
                return
            except Exception as e:
                await session.rollback()
                logger.exception("launch_task failed")
                await message.answer(_truncate(f"Ошибка Cursor API: {e}", 500))
                return
            await session.commit()
        lines = [
            f"Задача принята. Job #{job.id}",
            f"Агент: {job.cursor_agent_id or '—'}",
            f"Статус: {job.status.value}",
        ]
        if job.agent_url:
            lines.append(job.agent_url)
        await message.answer("\n".join(lines))

    @router.message(Command("task"))
    async def cmd_task(message: Message) -> None:
        if not message.from_user:
            return
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        text = (message.text or "").split(maxsplit=1)
        if len(text) < 2 or not text[1].strip():
            await message.answer("Использование: /task <описание задачи>")
            return
        prompt = text[1].strip()
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            p = await orch.get_active_project(message.chat.id)
            await session.commit()
        if p is None:
            await message.answer("Сначала выберите проект: /use <id>")
            return
        if settings.require_task_confirmation:
            await orch_prepare_and_confirm(message, redis, p.id, prompt)
            return
        await _launch_and_reply(
            message,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            project_id=p.id,
            prompt=prompt,
        )

    @router.callback_query(F.data == "wb_confirm")
    async def on_confirm(callback: CallbackQuery) -> None:
        if not callback.from_user or not callback.message:
            return
        try:
            check_telegram_allowed(callback.from_user.id)
        except ForbiddenError:
            await callback.answer("Нет доступа", show_alert=True)
            return
        pending = await redis.get_pending_task(callback.message.chat.id)
        if not pending:
            await callback.answer("Нет ожидающей задачи", show_alert=True)
            return
        project_id, prompt = pending
        await redis.clear_pending_task(callback.message.chat.id)
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=None)
        await _launch_and_reply(
            callback.message,
            user_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            project_id=project_id,
            prompt=prompt,
        )

    @router.callback_query(F.data == "wb_cancel")
    async def on_cancel(callback: CallbackQuery) -> None:
        await redis.clear_pending_task(callback.message.chat.id)
        await callback.answer("Отменено")
        await callback.message.edit_reply_markup(reply_markup=None)

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message) -> None:
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        await redis.clear_pending_task(message.chat.id)
        await message.answer("Ожидающая задача сброшена.")

    @router.message(Command("followup"))
    @router.message(Command("fu"))
    async def cmd_followup(message: Message) -> None:
        if not message.from_user:
            return
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer("Использование: /followup <текст> (или /fu <текст>)")
            return
        prompt = parts[1].strip()
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            try:
                agent_id = await orch.followup_agent(message.from_user.id, message.chat.id, prompt)
            except (NotFoundError, ForbiddenError) as e:
                await session.rollback()
                await message.answer(_deny_reason(e))
                return
            except Exception as e:
                await session.rollback()
                logger.exception("followup failed")
                await message.answer(_truncate(f"Ошибка Cursor API: {e}", 500))
                return
        await message.answer(_truncate(f"Follow-up отправлен агенту {agent_id}"))

    @router.message(Command("stop"))
    async def cmd_stop(message: Message) -> None:
        if not message.from_user:
            return
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        parts = (message.text or "").split()
        job_id: int | None = None
        if len(parts) >= 2:
            try:
                job_id = int(parts[1])
            except ValueError:
                await message.answer("job_id должен быть числом или опустите аргумент")
                return
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            try:
                job = await orch.stop_agent_job(message.from_user.id, message.chat.id, job_id)
            except (NotFoundError, ForbiddenError) as e:
                await session.rollback()
                await message.answer(_deny_reason(e))
                return
            except Exception as e:
                await session.rollback()
                logger.exception("stop failed")
                await message.answer(_truncate(f"Ошибка Cursor API: {e}", 500))
                return
        await message.answer(
            _truncate(f"Остановка запрошена. Job #{job.id}, статус: {job.status.value}, агент: {job.cursor_agent_id}")
        )

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not message.from_user:
            return
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            jobs = await orch.list_jobs_for_chat(message.chat.id, message.from_user.id, limit=15)
            await session.commit()
        if not jobs:
            await message.answer("Задач в этом чате пока нет.")
            return
        lines: list[str] = []
        for j in jobs:
            line = f"#{j.id} {j.status.value} — {j.prompt_preview[:120]}"
            if j.cursor_agent_id:
                line += f" [{j.cursor_agent_id}]"
            lines.append(line)
        await message.answer(_truncate("\n".join(lines)))

    @router.message(Command("repos"))
    async def cmd_repos(message: Message) -> None:
        try:
            check_telegram_allowed(message.from_user.id)
        except ForbiddenError as e:
            await message.answer(_deny_reason(e))
            return
        async with SessionLocal() as session:
            orch = _orch(session, cursor, redis)
            try:
                repos = await orch.list_cursor_repositories_cached()
            except Exception as e:
                await session.rollback()
                await message.answer(f"Не удалось получить список репозиториев: {e}")
                return
            await session.commit()
        if not repos:
            await message.answer("Список пуст")
            return
        lines = [f"{r.get('owner')}/{r.get('name')} — {r.get('repository')}" for r in repos[:40]]
        more = f"\n… и ещё {len(repos) - 40}" if len(repos) > 40 else ""
        await message.answer("\n".join(lines) + more)

    return router
