from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk, sql_in

# Fixed enum — CLAUDE.md §8. No sampling: every stage, every turn, writes a row.
LATENCY_STAGES = (
    "endpoint_detect",
    "asr_finalize",
    "prompt_assemble",
    "model_ttft",
    "first_chunk_assemble",
    "tts_first_chunk",
    "transport",
    "e2e",
)
MODEL_CALL_ROLES = ("persona", "endpointer", "narrator", "planner", "judge", "embedder")


class LatencyEvent(UUIDPk, TimestampMixin, Base):
    """A table, not a log line (CLAUDE.md §5) — the headline latency claim of this project has
    to be queryable, not grepped.
    """

    __tablename__ = "latency_events"
    __table_args__ = (
        CheckConstraint(sql_in("stage", LATENCY_STAGES), name="ck_latency_events_stage"),
        Index("ix_latency_events_session_turn", "session_id", "turn_id"),
        Index("ix_latency_events_stage_created_at", "stage", "created_at"),
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)


class ModelCall(UUIDPk, TimestampMixin, Base):
    """Every model invocation, no exceptions, no sampling (CLAUDE.md §8) — role, model, prompt
    version, tokens, TTFT, total latency, cost and cache status.
    """

    __tablename__ = "model_calls"
    __table_args__ = (
        CheckConstraint(sql_in("role", MODEL_CALL_ROLES), name="ck_model_calls_role"),
        Index("ix_model_calls_session_created_at", "session_id", "created_at"),
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable: not every call is turn-scoped (e.g. session-level planning).
    turn_id: Mapped[std_uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    role: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    ttft_ms: Mapped[float | None] = mapped_column(Float)
    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    cost_cents: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
