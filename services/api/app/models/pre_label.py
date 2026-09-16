from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import CheckConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk


class PreLabel(UUIDPk, TimestampMixin, Base):
    """docs/phase-5-BUILD.md TASK 5.3d: "Model pre-labelling (training split ONLY)... Human
    reviews and corrects every pre-label; the interface must not default to accept." A
    suggestion, not a label — deliberately not an `Annotation` row (that table represents a
    completed human judgement; `score` there is `NOT NULL` by design). Generated offline by
    services/training/annotate/pre_label.py, never by services/api itself — api has no model-call
    dependency anywhere else in this project and this doesn't introduce the first one; the admin
    queue only ever reads this table.
    """

    __tablename__ = "pre_labels"
    __table_args__ = (
        UniqueConstraint("turn_id", "criterion_key", name="uq_pre_labels_turn_criterion"),
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_pre_labels_score_range"),
    )

    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
