"""Settings for the Phase 5 offline tools (dataset build, synthetic generation, training,
eval). `services/training` is "not deployed" (CLAUDE.md's own directory layout) — a batch of
scripts, not a service with a request path — so unlike services/api/realtime/coach it imports
api's real ORM models directly (sys.path, same convention scripts/seed.py already uses) rather
than hand-mirroring the schema a third time. docs/decisions/0003's "independent services stay
independent" reasoning is about deployed services that must not couple their release cycles;
it doesn't apply to a script that reads the schema api already owns.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "services" / "api"
for _path in (str(REPO_ROOT), str(API_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402


class TrainingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str

    # TASK 5.2b: the model that generates synthetic answers. Deliberately reuses MODEL_JUDGE's
    # value rather than the persona models — this call never talks to a real user, so it isn't
    # subject to the persona's latency budget, and using the same model family the scorer
    # itself is prompted-baseline'd against keeps generation and scoring on comparable footing.
    training_generator_model: str = "groq/openai/gpt-oss-20b"

    # The one account whose sessions are tagged "self" (docs/phase-5-BUILD.md TASK 5.2a's
    # highest-fidelity, lowest-volume source). Every other real, training-consented user's
    # sessions are tagged "recruited". Unset by default — services/training/dataset/build.py
    # falls back to "the single real user in the dev DB" when there's exactly one, and warns
    # loudly when there's ambiguity it can't resolve on its own (see that module's docstring).
    training_self_user_email: str = ""

    synthetic_user_email: str = "synthetic-data@interactai.local"

    wandb_project: str = "interactai-scorer"
    wandb_mode: str = "offline"  # "online" needs a real WANDB_API_KEY; never assumed present.


@lru_cache
def get_training_settings() -> TrainingSettings:
    return TrainingSettings()
