from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from app import paths

# Absolute, and the same directory the uploads resolve to. The old default was
# relative to the working directory, so launching the server from anywhere but
# backend/ put the database somewhere the uploads were not.
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{paths.DB_PATH}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = _DEFAULT_DB_URL
    EXPORT_PROFILES_DIR: str = "./profiles"
    AI_PROVIDER: str = "anthropic"
    AI_API_KEY: str | None = None
    AI_MODEL: str | None = None
    SECRET_KEY: str = "change-me-in-production"


settings = Settings()
