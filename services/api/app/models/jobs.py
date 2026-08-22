"""docs/phase-2-BUILD.md TASK 2.2d: "After max_tries (3), write a failed_jobs record and
surface it. A report that never generates must be visible, not silent." Not one of Phase 0's
15 P0 tables (CLAUDE.md explicitly lists what NOT to add speculatively) — this one earns its
place now because Task 2.2d requires it directly, not speculatively.
"""

from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk, sql_in

FAILED_JOB_NAMES = ("score_turn", "generate_report")


class FailedJob(UUIDPk, TimestampMixin, Base):
    __tablename__ = "failed_jobs"
    __table_args__ = (
        CheckConstraint(sql_in("job_name", FAILED_JOB_NAMES), name="ck_failed_jobs_name"),
    )

    session_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[std_uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    job_name: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
