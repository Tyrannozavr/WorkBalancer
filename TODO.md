# WorkBalancer — что осталось сделать

Список бэклога после MVP (Telegram + Cursor Cloud Agents + webhook + Postgres/Redis).

## Продукт и Telegram

- [ ] Команда **follow-up** к уже запущенному агенту (`POST /v0/agents/{id}/followup`) — хранить `last_cursor_agent_id` в контексте чата или выбирать job по номеру.
- [ ] Команда **/stop** / остановка агента через Cursor API.
- [ ] Команда **/status** или список активных job по чату и пользователю.
- [ ] Улучшить UX: длинные сообщения, Markdown/HTML аккуратно, обрезка ошибок API.

## Веб / API (presentation/web)

- [ ] REST для тех же сценариев, что и в Telegram (проекты, запуск задачи, опционально — только для внутренней сети + API key).
- [ ] OpenAPI (описание схем) для фронта и интеграций.

## Frontend

- [ ] Папка `frontend/` пока пустая: выбор стека (React/Vue/Svelte), экран «проекты», при желании — дублирование сценариев бота.

## Инфраструктура и прод

- [ ] **HTTPS** для `PUBLIC_BASE_URL`: пример `nginx` с `listen 443 ssl`, сертификаты (Let’s Encrypt / свои).
- [ ] Секреты вне `.env` в проде: Vault / секреты оркестратора.
- [ ] Health/readiness: проверка БД и Redis при необходимости.
- [ ] Логи/метрики: структурированные логи, при необходимости Prometheus + алерты.

## CI/CD

- [ ] GitHub Actions: `pytest` (с `SKIP_INTEGRATION=1` в PR), `ruff`/`mypy` по желанию.
- [ ] Отдельный workflow для интеграционных тестов с Docker (по расписанию или в main).

## Качество и тесты

- [ ] Поднять покрытие: **handlers Telegram** (`bot.py`), **lifespan/poll** в `main.py` — через aiogram test utils или тонкие интеграционные тесты.
- [ ] Интеграционные тесты с БД в CI (Docker service postgres + redis).

## Безопасность и доступ

- [ ] Режим «несколько пользователей» / роли (если бот не только личный).
- [ ] Rate limit на `/webhooks/cursor` и при необходимости на Telegram-команды.
- [ ] Явный allowlist репозиториев GitHub (по URL или org) вместо только списка проектов в БД.

## Документация

- [ ] Краткий **README**: как заполнить `.env`, запуск `docker compose`, получение `PUBLIC_BASE_URL` для Cursor.

---

*Обновляйте этот файл по мере закрытия пунктов; при необходимости дублируйте ключевые правила в `.cursor/rules/`.*
