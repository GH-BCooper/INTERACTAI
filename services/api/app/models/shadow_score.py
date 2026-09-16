from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk


class ShadowScore(UUIDPk, TimestampMixin, Base):
    """docs/phase-5-BUILD.md TASK 5.5d: "The prompted baseline runs alongside the fine-tune on
    a sampled fraction (10%) of live turns, writing to turn_scores with its own model_version."

    Written here, not `turn_scores`, per docs/decisions/0021: `turn_scores` has a UNIQUE
    constraint on `(turn_id, criterion_key)` only — no `model_version` column in that key — set
    in Phase 0 and load-bearing for every existing aggregation/report/evidence code path
    (CLAUDE.md §5's own "turn_metrics and turn_scores are separate tables and must stay
    separate" spirit extends to not silently widening either one's identity late in the
    project). A shadow score is never shown to a user and never feeds aggregation — this table
    exists purely so a live comparison-over-time query can run without touching the frozen
    production table at all.
    """

    __tablename__ = "shadow_scores"
    __table_args__ = (
        UniqueConstraint(
            "turn_id", "criterion_key", "model_version",
            name="uq_shadow_scores_turn_criterion_model",
        ),
        CheckConstraint(
            "score IS NULL OR score BETWEEN 1 AND 5", name="ck_shadow_scores_score_range"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_shadow_scores_confidence_range"),
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
