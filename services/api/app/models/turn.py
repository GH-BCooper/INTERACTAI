from __future__ import annotations

import uuid as std_uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, sql_in, uuid7

TURN_SPEAKERS = ("user", "persona")


class Turn(Base):
    """Partitioned by month on created_at — see docs/decisions/0002-turns-partitioning-and-fk.md
    for why its primary key is composite `(id, created_at)` and why child tables reference
    `sessions.id`, not `turns.id`, for their cascade FK.
    """

    __tablename__ = "turns"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "index", "created_at", name="uq_turns_session_index_created_at"
        ),
        CheckConstraint(sql_in("speaker", TURN_SPEAKERS), name="ck_turns_speaker"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    word_timings: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    asr_confidence: Mapped[float | None] = mapped_column(Float)


class TurnMetrics(Base):
    """Deterministic only — arithmetic on the transcript and timestamps. No model ever writes
    here (CLAUDE.md §5). 1:1 with a turn.
    """

    __tablename__ = "turn_metrics"
    __table_args__ = (UniqueConstraint("turn_id", name="uq_turn_metrics_turn_id"),)

    id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    wpm: Mapped[float] = mapped_column(Float, nullable=False)
    filler_count: Mapped[int] = mapped_column(Integer, nullable=False)
    filler_rate: Mapped[float] = mapped_column(Float, nullable=False)
    longest_pause_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    speech_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)


class TurnScore(Base):
    """A model judgement — sometimes wrong, unlike turn_metrics. Kept in a separate table on
    purpose (CLAUDE.md §5) so the UI never presents arithmetic and judgement with equal
    authority. `evidence_spans` are char offsets into `turns.text`, verified by exact substring
    match before this row is written (CLAUDE.md §1.5) — that verification happens in
    services/coach, not here; this table just stores the result.
    """

    __tablename__ = "turn_scores"
    __table_args__ = (
        UniqueConstraint("turn_id", "criterion_key", name="uq_turn_scores_turn_criterion"),
        CheckConstraint(
            "score IS NULL OR score BETWEEN 1 AND 5", name="ck_turn_scores_score_range"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_turn_scores_confidence_range"),
    )

    id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL when confidence is below threshold — CLAUDE.md §1.6, "not enough signal, never a number".
    score: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # {start, end} char offsets into turns.text — CLAUDE.md §1.5.
    evidence_spans: Mapped[list[dict[str, int]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    # The scorer's own explanation (docs/phase-2-BUILD.md TASK 2.5b's `CriterionScore.
    # rationale`) — never shown to the user as-is (CLAUDE.md §1.4: prose to the UI comes from
    # the narrator, not the scorer) and never fed back into scoring. Kept for report-author
    # debugging and as narrator context.
    rationale: Mapped[str | None] = mapped_column(Text)
