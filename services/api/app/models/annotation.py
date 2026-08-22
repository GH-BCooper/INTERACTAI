from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk


class Annotation(UUIDPk, TimestampMixin, Base):
    """A human label. `round` lets the same item be labelled independently more than once —
    without it, inter-annotator agreement (Phase 5) can't be computed (CLAUDE.md §5).
    """

    __tablename__ = "annotations"
    __table_args__ = (
        UniqueConstraint(
            "turn_id", "annotator_id", "criterion_key", "round",
            name="uq_annotations_turn_annotator_criterion_round",
        ),
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_annotations_score_range"),
        CheckConstraint("round >= 1", name="ck_annotations_round_positive"),
        Index("ix_annotations_turn_criterion", "turn_id", "criterion_key"),
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    annotator_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
