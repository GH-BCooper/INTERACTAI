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
        # Covering index (migration b8c9d0e1f2a3): the e2e percentile query is index-only.
        Index(
            "ix_latency_events_stage_created_at_cover",
            "stage",
            "created_at",
            postgresql_include=["duration_ms", "session_id", "turn_id", "host_class"],
        ),
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    # Phase 6 TASK 6.1a: filter by host class. NULL for rows written before it was recorded.
    host_class: Mapped[str | None] = mapped_column(Text)


class ModelCall(UUIDPk, TimestampMixin, Base):
    """Every model invocation, no exceptions, no sampling (CLAUDE.md §8) — role, model, prompt
    version, tokens, TTFT, total latency, cost and cache status.
    """

    __tablename__ = "model_calls"
    __table_args__ = (
        CheckConstraint(sql_in("role", MODEL_CALL_ROLES), name="ck_model_calls_role"),
        Index("ix_model_calls_session_created_at", "session_id", "created_at"),
        Index("ix_model_calls_created_at", "created_at"),
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


DEPLOYMENT_KINDS = ("model_promoted", "model_rolled_back", "prompt_version", "service_deploy")


class DeploymentEvent(UUIDPk, TimestampMixin, Base):
    """Phase 6 TASK 6.2: the markers on the regression chart. A metric that moved is only
    explicable if you can see what shipped just before it moved."""

    __tablename__ = "deployment_events"
    __table_args__ = (
        CheckConstraint(sql_in("kind", DEPLOYMENT_KINDS), name="ck_deployment_events_kind"),
        Index("ix_deployment_events_created_at", "created_at"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    model_version_id: Mapped[std_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="SET NULL")
    )
