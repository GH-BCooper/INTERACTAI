"""Settings, loaded once from the repo-root .env regardless of the process's cwd.

Mirrors services/api/app/core/config.py's resolution strategy exactly (file-location-based,
not cwd-based) — realtime runs via `uvicorn --app-dir services/realtime`, same constraint.

Only ws_token_secret is needed here, never jwt_secret/app_secret: realtime only ever validates
a WS_TOKEN_SECRET-signed, single-use token minted by the API service. It never mints or
verifies an access/refresh token itself (CLAUDE.md §1.3, docs/phase-0-BUILD.md TASK 0.5).
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

    ws_token_secret: str
    database_url: str
    redis_url: str

    max_concurrent_sessions: int = 4

    # ── Recording storage (Task 1.1/1.2c: "upload the recording") ───────────────
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True

    # ── Speech ──────────────────────────────────────────────────────────────────
    asr_model: str = "base.en"
    asr_compute_type: str = "int8"
    asr_device: str = "cpu"
    vad_model_path: str = "./models/vad/silero_vad.onnx"
    piper_voice_dir: str = "./models/piper"
    default_piper_voice: str = "en_US-lessac-medium"
    secondary_piper_voice: str = "en_US-ryan-medium"
    # Every voice_id any seeded persona actually uses (content/personas/*.yaml) — the
    # backchannel and idle-prompt caches (Task 1.5b/2.1) are preloaded for all of these at
    # startup, not just the default, since a session's persona voice is rarely the default one.
    persona_voice_ids: tuple[str, ...] = ("en_US-lessac-medium", "en_US-ryan-medium")

    # ── Audio contract — FROZEN. See docs/03-realtime-protocol.md. ──────────────
    audio_sample_rate: int = 16000
    audio_frame_ms: int = 20
    audio_channels: int = 1
    jitter_buffer_ms: int = 120

    # ── Latency budget (ms) ───────────────────────────────────────────────────
    budget_e2e_p50: int = 1100
    budget_e2e_p95: int = 1400

    # ── Endpointing cascade (docs/phase-1-BUILD.md TASK 1.3) ─────────────────
    endpoint_base_silence_ms: int = 500
    endpoint_min_silence_ms: int = 350
    endpoint_max_silence_ms: int = 900
    endpoint_min_utterance_ms: int = 400
    endpoint_max_turn_ms: int = 120_000
    semantic_endpoint_timeout_ms: int = 80

    # ── Model roles used on the realtime path ────────────────────────────────
    max_tokens_per_turn: int = 180
    max_tokens_per_session: int = 12_000
    model_persona: str = "groq/openai/gpt-oss-20b"
    model_persona_local: str = "ollama/qwen2.5:3b-instruct"
    model_endpointer: str = "ollama/qwen2.5:0.5b-instruct"
    model_planner: str = "groq/openai/gpt-oss-20b"
    model_narrator: str = "groq/openai/gpt-oss-20b"
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Persona agent (docs/phase-2-BUILD.md TASK 2.3) ───────────────────────
    backchannel_rate_max: float = 1.0 / 3.0  # Task 2.4: "at most 1 in 3 turns"
    backchannel_enabled: bool = True
    memory_compaction_every_n_turns: int = 6

    # ── Session lifecycle (Task 1.1) ─────────────────────────────────────────
    handshake_timeout_s: float = 5.0
    resume_grace_s: float = 90.0
    sweeper_interval_s: float = 15.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
