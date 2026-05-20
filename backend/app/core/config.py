"""Centralised application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    allowed_origins: str = Field(default="http://localhost:5173")

    openrouter_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    brave_api_key: str = Field(default="")
    balldontlie_api_key: str = Field(default="")
    reddit_user_agent: str = Field(default="")

    # Where the evaluation SQLite database lives. Defaults to
    # ``data/eval.db`` at the project root; override via env var
    # ``EVAL_DB_PATH`` for tests or CI.
    eval_db_path: str = Field(default="")

    # Brief memory (RAG over past Daily Briefs for NBA Copilot).
    memory_db_path: str = Field(default="")
    memory_enabled: bool = Field(default=True)
    memory_embedding_model: str = Field(default="openai/text-embedding-3-small")
    memory_default_days: int = Field(default=14, ge=1, le=365)
    memory_search_top_k: int = Field(default=6, ge=1, le=20)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def has_openrouter(self) -> bool:
        return bool(self.openrouter_api_key.strip())

    @property
    def has_brave(self) -> bool:
        return bool(self.brave_api_key)

    @property
    def has_balldontlie(self) -> bool:
        return bool(self.balldontlie_api_key.strip())

    @property
    def resolved_eval_db_path(self) -> Path:
        """Resolve the eval DB path, falling back to ``<root>/data/eval.db``."""
        if self.eval_db_path:
            return Path(self.eval_db_path).expanduser().resolve()
        return PROJECT_ROOT / "data" / "eval.db"

    @property
    def resolved_memory_db_path(self) -> Path:
        """Resolve the brief-memory DB path, falling back to ``<root>/data/memory.db``."""
        if self.memory_db_path:
            return Path(self.memory_db_path).expanduser().resolve()
        return PROJECT_ROOT / "data" / "memory.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
