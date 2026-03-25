from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cursor_api_key: str = ""
    public_base_url: str = "http://localhost:8080"
    cursor_webhook_secret: str = ""

    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""

    database_url: str = "postgresql+asyncpg://workbalancer:workbalancer@localhost:5432/workbalancer"
    redis_url: str = "redis://localhost:6379/0"

    max_parallel_agents_per_user: int = 2
    require_task_confirmation: bool = True

    cursor_api_base: str = "https://api.cursor.com"

    @property
    def allowed_telegram_user_ids_set(self) -> set[int]:
        if not self.telegram_allowed_user_ids.strip():
            return set()
        return {int(x.strip()) for x in self.telegram_allowed_user_ids.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
