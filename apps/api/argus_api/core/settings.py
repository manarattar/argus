"""Application configuration.

Everything environment-dependent lives here, loaded from ``.env`` and the
process environment. Nothing that varies between a laptop, a demo deployment
and a production deployment should be written into code anywhere else.

The default configuration is deliberately the zero-friction one: SQLite, the
local lexical embedder and Demo Mode. A fresh clone runs with no accounts and
no external services. Adding one line to ``.env`` switches the same code path
to live inference.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]

ModelBackend = Literal["auto", "openai", "anthropic", "replay"]


class Settings(BaseSettings):
    """Typed view of the environment."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    # -- application ----------------------------------------------------
    app_name: str = "ARGUS"
    environment: Literal["local", "docker", "test", "production"] = "local"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"

    # Comma-separated list; parsed by the validator below.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # -- storage --------------------------------------------------------
    # SQLite by default so first run needs no container. docker-compose sets
    # this to the Postgres/pgvector service instead; the ORM layer is identical.
    database_url: str = Field(default=f"sqlite:///{REPO_ROOT / 'data' / 'argus.db'}")

    # -- model backend --------------------------------------------------
    # "auto" resolves to live inference when a token is present, and to replay
    # otherwise, so behaviour degrades predictably rather than crashing.
    model_backend: ModelBackend = "auto"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    model_name: str = "gpt-4o-mini"
    model_temperature: float = 0.0
    model_max_tokens: int = 4096
    model_max_attempts: int = 3

    # Capture live exchanges into data/recordings so Demo Mode can serve them.
    record_llm_calls: bool = False
    recordings_dir: Path = REPO_ROOT / "data" / "recordings"

    # -- embeddings -----------------------------------------------------
    embedding_provider: Literal["auto", "openai", "local"] = "auto"
    embedding_model: str = "text-embedding-3-small"

    # -- data -----------------------------------------------------------
    demo_data_dir: Path = REPO_ROOT / "data" / "demo"
    policy_data_dir: Path = REPO_ROOT / "data" / "policies"
    eval_data_dir: Path = REPO_ROOT / "data" / "evals"

    # -- limits ---------------------------------------------------------
    max_upload_bytes: int = 5 * 1024 * 1024
    allowed_upload_suffixes: str = ".txt,.md"
    rate_limit_per_minute: int = 120

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def upload_suffixes(self) -> set[str]:
        return {s.strip().lower() for s in self.allowed_upload_suffixes.split(",") if s.strip()}

    @property
    def has_live_model(self) -> bool:
        """Whether a live backend could actually be constructed."""
        if self.model_backend == "replay":
            return False
        if self.model_backend == "anthropic":
            return bool(self.anthropic_api_key)
        if self.model_backend == "openai":
            return bool(self.openai_api_key)
        return bool(self.openai_api_key or self.anthropic_api_key)

    @property
    def demo_mode(self) -> bool:
        """True when the app is serving recorded completions."""
        return not self.has_live_model

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
