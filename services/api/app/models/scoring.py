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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk, sql_in

REPORT_STATUSES = ("pending", "ready", "failed")


class SessionScore(UUIDPk, TimestampMixin, Base):
    """Per-criterion rollup across the whole session — the aggregate a report displays,
    distinct from the per-turn detail in turn_scores (CLAUDE.md §5).
    """

    __tablename__ = "session_scores"
    __table_args__ = (
        UniqueConstraint("session_id", "criterion_key", name="uq_session_scores_session_criterion"),
        CheckConstraint(
            "aggregate_score IS NULL OR aggregate_score BETWEEN 1 AND 5",
            name="ck_session_scores_score_range",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_session_scores_confidence_range"),
        CheckConstraint(
            "percentile_vs_self IS NULL OR percentile_vs_self BETWEEN 0 AND 1",
            name="ck_session_scores_percentile_range",
        ),
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_turn_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    # docs/phase-2-BUILD.md TASK 2.5f: "computed against the user's own history for the same
    # scenario family." Nullable — the user's first session in a family has no history to
    # compare against, and that is a fact to represent, not an error (CLAUDE.md §10, "never
    # fabricate a metric").
    percentile_vs_self: Mapped[float | None] = mapped_column(Float)


class Report(UUIDPk, TimestampMixin, Base):
    """The final generated report artefact (CLAUDE.md §7 — the coach's output). Prose here
    comes from the narrator model, which is handed already-fixed scores and evidence and is
    forbidden from contradicting them (CLAUDE.md §1.4).
    """

    __tablename__ = "reports"
    __table_args__ = (CheckConstraint(sql_in("status", REPORT_STATUSES), name="ck_reports_status"),)

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    summary: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    growth_areas: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    # docs/phase-2-BUILD.md TASK 2.5g: "three concrete next actions — each tied to a specific
    # turn_id." A flat ARRAY can't carry that pairing, hence JSONB:
    # [{"text": str, "turn_id": str | null}, ...].
    next_actions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    highlight_turn_id: Mapped[std_uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lowlight_turn_id: Mapped[std_uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    # Task 2.5's edge-case table: "Session has 2 turns -> report generates but flags low sample
    # size explicitly." A boolean the narrator's post-check and the report UI can both trust
    # without re-deriving turn counts from turns_scores.
    low_sample_size: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    narrator_model_version: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
