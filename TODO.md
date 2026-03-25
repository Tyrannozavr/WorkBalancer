# WorkBalancer — что осталось сделать

Список бэклога после MVP (Telegram + Cursor Cloud Agents + webhook + Postgres/Redis).

## Продукт и Telegram

- [x] Команда **follow-up** к уже запущенному агенту (`POST /v0/agents/{id}/followup`) — Redis `last_agent` + `/followup` / `/fu`.
- [x] Команда **/stop** / остановка агента через Cursor API.
- [x] Команда **/status** — последние job в чате для пользователя.
- [x] Частично: обрезка длинных ответов и ошибок (`_truncate`).

## Веб / API (presentation/web)

- [ ] REST для тех же сценариев, что и в Telegram (проекты, запуск задачи, опционально — только для внутренней сети + API key).
- [ ] OpenAPI (описание схем) для фронта и интеграций.

## Frontend

- [ ] Папка `frontend/` пока пустая: выбор стека (React/Vue/Svelte), экран «проекты», при желании — дублирование сценариев бота.

## Инфраструктура и прод

- [x] Пример **HTTPS** для nginx: `nginx/conf.d/ssl.example.conf` (подключить сертификаты и volume).
- [ ] Секреты вне `.env` в проде: Vault / секреты оркестратора.
- [x] **GET /health/ready** — проверка PostgreSQL и Redis.
- [ ] Логи/метрики: структурированные логи, при необходимости Prometheus + алерты.

## CI/CD

- [x] GitHub Actions: `pytest` с `SKIP_INTEGRATION=1` на push/PR в `main` и `develop`.
- [ ] Отдельный workflow для интеграционных тестов с Docker (по расписанию или в main).

## Качество и тесты

- [ ] Поднять покрытие: **handlers Telegram** (`bot.py`), **lifespan/poll** в `main.py`.
- [ ] Интеграционные тесты с БД в CI (Docker service postgres + redis).

## Безопасность и доступ

- [ ] Режим «несколько пользователей» / роли (если бот не только личный).
- [ ] Rate limit на `/webhooks/cursor` и при необходимости на Telegram-команды.
- [ ] Явный allowlist репозиториев GitHub (по URL или org) вместо только списка проектов в БД.

## Документация

- [x] Краткий **README**: `.env`, docker compose, `PUBLIC_BASE_URL`.

---

*Обновляйте этот файл по мере закрытия пунктов; при необходимости дублируйте ключевые правила в `.cursor/rules/`.*
