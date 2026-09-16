"""Settings, loaded once from the repo-root .env regardless of the process's cwd.

Resolved by file location rather than cwd because api/realtime run with cwd == repo root
(uvicorn --app-dir) while alembic runs with cwd == services/api (`uv run --directory`) — see
Makefile. Both need the same .env.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "development"
    log_level: str = "info"

    app_secret: str
    jwt_secret: str
    ws_token_secret: str

    web_origin: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    realtime_ws_url: str = "ws://localhost:8080/ws"

    database_url: str
    redis_url: str

    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True

    github_client_id: str = ""
    github_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    # Phase 6 TASK 6.4d (AS-12): self-host with zero external keys means no OAuth app. This
    # enables GET /auth/local/login — one local account, no password. Refused in production.
    self_host_local_login: bool = False

    max_concurrent_sessions: int = 4
    max_sessions_per_hour: int = 10
    max_sessions_per_day: int = 40
    auth_rate_limit_per_minute: int = 30

    max_tokens_per_turn: int = 180
    max_tokens_per_session: int = 12000
    max_cents_per_user_month: int = 200

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    ws_token_ttl_seconds: int = 120
    oauth_state_ttl_seconds: int = 600

    @model_validator(mode="after")
    def _distinct_secrets(self) -> Self:
        if self.jwt_secret == self.ws_token_secret:
            raise ValueError(
                "JWT_SECRET and WS_TOKEN_SECRET must be different — a leaked ws token must "
                "cost exactly one practice session, not an account (CLAUDE.md §, Task 0.5)."
            )
        if self.jwt_secret == self.app_secret:
            raise ValueError("JWT_SECRET and APP_SECRET must be different.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
