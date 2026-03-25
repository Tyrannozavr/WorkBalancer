# WorkBalancer

Оркестратор: **Telegram** (aiogram 3) + **Cursor Cloud Agents API** + **PostgreSQL** + **Redis** + **nginx**.

## Требования

- Docker / Docker Compose (для Postgres, Redis, backend, nginx)
- Python 3.11+ (локальная разработка backend)
- Аккаунт Cursor, API key и доступ Cloud Agents к нужным репозиториям GitHub
- Публичный **HTTPS** URL для вебхуков Cursor (`PUBLIC_BASE_URL`)

## Быстрый старт

1. Скопируйте `.env.example` в `.env` в корне репозитория и заполните:

   - `CURSOR_API_KEY` — [Cursor Dashboard](https://cursor.com/settings)
   - `CURSOR_WEBHOOK_SECRET` — не менее 32 символов (тот же секрет указывается при запуске агента)
   - `PUBLIC_BASE_URL` — базовый URL вашего backend **с HTTPS** (например `https://wb.example.com`), без слэша в конце; Cursor будет слать `POST {PUBLIC_BASE_URL}/webhooks/cursor`
   - `TELEGRAM_BOT_TOKEN` — от [@BotFather](https://t.me/BotFather)
   - `TELEGRAM_ALLOWED_USER_IDS` — числовые id пользователей Telegram через запятую

2. Запуск стека:

   ```bash
   docker compose up --build
   ```

   HTTP: порт **8080** (nginx → backend). Настройте DNS и TLS для домена, укажите этот URL в `PUBLIC_BASE_URL`.

3. Локальные тесты backend:

   ```bash
   cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
   SKIP_INTEGRATION=1 .venv/bin/python -m pytest tests/ -q
   ```

## Команды Telegram (кратко)

| Команда | Действие |
|---------|----------|
| `/add`, `/use`, `/projects` | Проекты и активный репозиторий |
| `/task` | Запуск агента Cursor |
| `/followup` / `/fu` | Уточнение к последнему агенту |
| `/stop [job_id]` | Остановка агента |
| `/status` | Последние задачи в чате |

## Ветки (gitflow)

`main` — стабильная ветка, `develop` — разработка. См. `.cursor/rules/workbalancer-gitflow.mdc`.
