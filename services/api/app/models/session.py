from __future__ import annotations

import uuid as std_uuid
from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk, sql_in

SESSION_STATUSES = ("created", "active", "closing", "closed", "failed")
SESSION_END_REASONS = (
    "user_hangup",
    "duration_reached",
    "persona_concluded",
    "budget_exhausted",
    "distress_exit",
    "error",
)
TARGET_MINUTES_CHOICES = (5, 10, 20, 30)
RECORDING_FORMATS = ("wav", "opus")


class Session(UUIDPk, TimestampMixin, Base):
    """One practice session. `brief` is the compiled-and-frozen session brief — resolved
    persona prompt reference, opening strategy, rubric id, difficulty parameters and budget
    caps — set once at creation and never mutated (docs/phase-0-BUILD.md TASK 0.5, "Session
    creation requirements"). That immutability is what makes a run reproducible.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(sql_in("status", SESSION_STATUSES), name="ck_sessions_status"),
        CheckConstraint(
            f"end_reason IS NULL OR {sql_in('end_reason', SESSION_END_REASONS)}",
            name="ck_sessions_end_reason",
        ),
        CheckConstraint(
            f"target_minutes IN {TARGET_MINUTES_CHOICES}", name="ck_sessions_target_minutes"
        ),
        CheckConstraint(
            f"recording_format IS NULL OR {sql_in('recording_format', RECORDING_FORMATS)}",
            name="ck_sessions_recording_format",
        ),
    )

    user_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    end_reason: Mapped[str | None] = mapped_column(Text)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    focus_areas: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    resume_text_override: Mapped[str | None] = mapped_column(Text)
    brief: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # The persona's question plan (docs/phase-2-BUILD.md TASK 2.3b): {topics: [{id, topic,
    # depth, minutes, status, followups_used}], elapsed_minutes, pending_obligation}. Generated
    # once at session start, updated after every turn. Nullable — plan generation is explicitly
    # allowed to fail without blocking the session (falls back to opening_strategy), and a
    # session that never got far enough to generate one is still a valid row. Unlike `brief`,
    # this is NOT frozen — it is the one piece of session state that mutates over the session's
    # lifetime by design.
    question_plan: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    # docs/phase-3-BUILD.md TASK 3.3a/3.4d — written once by services/realtime at finalize
    # (CLAUDE.md §2: api never touches audio itself, only reads this metadata to mint a
    # presigned URL). NULL means nothing was ever recorded — a session with zero completed
    # turns is a legitimate case, not an error (docs/decisions/0012).
    recording_key: Mapped[str | None] = mapped_column(Text)
    recording_format: Mapped[str | None] = mapped_column(Text)
    # ~1000-bucket precomputed waveform peaks, Task 3.3a — never decoded from audio client-side.
    peaks: Mapped[list[float] | None] = mapped_column(JSONB)
    # Task 3.4f "retry one question" — links a short single-question follow-up session back to
    # the original it re-asks. retry_of_turn_id has no FK for the same reason turn_id columns
    # elsewhere in this schema don't (docs/decisions/0002: turns is partitioned).
    retry_of_session_id: Mapped[std_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), index=True
    )
    retry_of_turn_id: Mapped[std_uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
