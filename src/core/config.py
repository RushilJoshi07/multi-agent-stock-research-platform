from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from the environment, then `.env`. Defaults match `.env.example`, so a fresh
    checkout works against the Compose services without a `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = "postgresql://fathom:change-me-local@localhost:5433/fathom"
    database_url_test: str = "postgresql://fathom:change-me-local@localhost:5433/fathom_test"
    redis_url: str = "redis://localhost:6380/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
