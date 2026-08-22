from __future__ import annotations

import uuid as std_uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk


class User(UUIDPk, TimestampMixin, Base):
    """Auth identity. GitHub/Google OAuth accounts link here by provider id — see
    services/api/app/services/auth.py. No password: OAuth-only per docs/phase-0-BUILD.md 0.5.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    github_id: Mapped[str | None] = mapped_column(Text, unique=True)
    google_id: Mapped[str | None] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Profile(UUIDPk, TimestampMixin, Base):
    """1:1 with users. `resume_text` is deletable independently of the profile row (granular
    consent) — clearing it is a PATCH that nulls the column, not a row delete.
    """

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "resume_text IS NULL OR length(resume_text) > 0", name="ck_profiles_resume_not_blank"
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
