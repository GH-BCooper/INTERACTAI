from __future__ import annotations

import uuid as std_uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk, sql_in

ONBOARDING_GOALS = ("job_interview", "technical_interview", "salary_negotiation")
EXPERIENCE_LEVELS = ("student", "early_career", "mid_level", "senior", "staff_plus")
PROVIDER_NAMES = ("groq",)
CONNECTION_TEST_STATUSES = ("untested", "success", "failed")
# 0 is the literal "delete immediately after scoring" tier from Task 4.4's privacy table —
# stored as an int rather than a nullable sentinel so a plain `<=` comparison in the expiry
# job (scripts/expire_recordings.py) never needs a NULL-vs-zero special case.
MIN_AUDIO_RETENTION_DAYS = 0
MAX_AUDIO_RETENTION_DAYS = 365


class User(UUIDPk, TimestampMixin, Base):
    """Auth identity. GitHub/Google OAuth accounts link here by provider id — see
    services/api/app/services/auth.py. No password: OAuth-only per docs/phase-0-BUILD.md 0.5.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"audio_retention_days BETWEEN {MIN_AUDIO_RETENTION_DAYS} "
            f"AND {MAX_AUDIO_RETENTION_DAYS}",
            name="ck_users_audio_retention_days_range",
        ),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    github_id: Mapped[str | None] = mapped_column(Text, unique=True)
    google_id: Mapped[str | None] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Task 4.4/4.5 — Privacy settings ──────────────────────────────────────────────────────
    # AS-04: "Training consent is a separate, revocable toggle. Never bundled into terms
    # acceptance." This is the account-level default a new session's own Consent row (see
    # models/consent.py) is initialised from; revoking it here cascades onto every turn the
    # user has already contributed under a granted consent (services/user_service.py
    # revoke_training_consent).
    training_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audio_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # ── Task 4.4 — Models settings (BYOK, routing policy) ────────────────────────────────────
    # A single global toggle rather than genuinely per-role routing — the acceptance criteria
    # this phase is actually held to ("[ ] Provider connection test reports success and failure
    # accurately") don't require per-role granularity, and CLAUDE.md's routing is already
    # config-driven (MODEL_PERSONA vs MODEL_PERSONA_LOCAL); this is a user-facing *preference*
    # signal recorded for a future session-brief read, not a live rewrite of that routing.
    prefer_local_models: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Task 4.3 — Onboarding ────────────────────────────────────────────────────────────────
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Profile(UUIDPk, TimestampMixin, Base):
    """1:1 with users. `resume_text` is deletable independently of the profile row (granular
    consent) — clearing it is a PATCH that nulls the column, not a row delete.
    """

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "resume_text IS NULL OR length(resume_text) > 0", name="ck_profiles_resume_not_blank"
        ),
        CheckConstraint(
            f"goal IS NULL OR {sql_in('goal', ONBOARDING_GOALS)}", name="ck_profiles_goal"
        ),
        CheckConstraint(
            f"experience_level IS NULL OR {sql_in('experience_level', EXPERIENCE_LEVELS)}",
            name="ck_profiles_experience_level",
        ),
        CheckConstraint(
            "speaking_rate BETWEEN 0.5 AND 2.0", name="ck_profiles_speaking_rate_range"
        ),
    )

    user_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    resume_text: Mapped[str | None] = mapped_column(Text)
    resume_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_role: Mapped[str | None] = mapped_column(Text)

    # ── Task 4.3 — Onboarding steps 1/2 ──────────────────────────────────────────────────────
    goal: Mapped[str | None] = mapped_column(Text)
    experience_level: Mapped[str | None] = mapped_column(Text)
    focus_areas: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    # ── Task 4.4 — Audio settings ────────────────────────────────────────────────────────────
    captions_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    speaking_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    noise_suppression: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    echo_cancellation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProviderCredential(UUIDPk, TimestampMixin, Base):
    """Task 4.4 — bring-your-own-key. `encrypted_api_key` is Fernet-encrypted at rest
    (core/crypto.py, keyed off APP_SECRET) and never leaves this table in plaintext — not in a
    log line, not in a response body (see schemas/user.py's ProviderCredentialOut, which has no
    key field at all, only `has_key`/`last_test_status`).
    """

    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_provider_credentials_user_provider"),
        CheckConstraint(
            sql_in("provider", PROVIDER_NAMES), name="ck_provider_credentials_provider"
        ),
        CheckConstraint(
            sql_in("last_test_status", CONNECTION_TEST_STATUSES),
            name="ck_provider_credentials_last_test_status",
        ),
    )

    user_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    last_test_status: Mapped[str] = mapped_column(Text, nullable=False, default="untested")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
