"""Settings — same file-location resolution and shape as services/api/app/core/config.py and
services/realtime/app/core/config.py (docs/decisions/0003's "shared contract, no shared code"
applies to coach too: it's an independent uv workspace member).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "development"
    log_level: str = "info"

    database_url: str
    redis_url: str

    # ── Model roles used off the latency path (CLAUDE.md §2: the coach never runs on it) ────
    model_judge: str = "groq/openai/gpt-oss-20b"
    model_narrator: str = "groq/openai/gpt-oss-20b"
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Scoring (docs/phase-2-BUILD.md TASK 2.5) ─────────────────────────────────────────────
    confidence_threshold: float = 0.6  # Task 2.5e: below this, "not enough signal", never a number
    scorer_impl: str = "prompted"  # "prompted" | "finetuned" (Phase 5) — CS interface seam

    max_job_tries: int = 3  # Task 2.2d: after this many, write a failed_jobs record


@lru_cache
def get_settings() -> Settings:
    return Settings()
