from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk

# Task 4.5a: "the consent text version stored" — bumped whenever the consent copy changes.
# Lives here, not in content/, because it's a legal/product record, not persona/rubric content.
CURRENT_CONSENT_VERSION = "2026-08-23.v1"


class Consent(UUIDPk, TimestampMixin, Base):
    """One row per session (Task 4.5a): "A consent record per session: recording_consent and
    training_consent as two separate booleans, timestamped, with the consent text version
    stored." Deliberately not merged into `sessions` itself — a session can exist without a
    consent decision ever having been shown (every session created before this phase, and any
    created through a path that isn't the recruited-session consent screen), and keeping this
    as its own nullable-relationship table means "no consent row" and "consent explicitly
    declined" stay distinguishable rather than collapsing to the same boolean.
    """

    __tablename__ = "consents"

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    recording_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    training_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
