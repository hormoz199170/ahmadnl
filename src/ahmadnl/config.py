from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    telegram_bot_token: str = Field(default="", repr=False)
    database_url: str = "sqlite+aiosqlite:///./ahmadnl.db"
    storage_dir: Path = Path("./storage")
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-1.5-flash"
    pdf_max_bytes: int = 10 * 1024 * 1024
    pdf_max_pages: int = 80
    ai_max_input_chars: int = 60_000
    ai_max_output_tokens: int = 1_200
    ai_timeout_seconds: int = 30
    ai_max_retries: int = 2
    ai_concurrency: int = 2
    daily_free_credits: int = 3
    summary_credit_cost: int = 1
    key_points_credit_cost: int = 1
    study_questions_credit_cost: int = 1
    answer_guidance_credit_cost: int = 1
    dev_purchases_enabled: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate_runtime(self) -> None:
        if not self.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        if self.is_production and not self.database_url.startswith("postgresql+"):
            raise RuntimeError("Production requires PostgreSQL SQLAlchemy URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
