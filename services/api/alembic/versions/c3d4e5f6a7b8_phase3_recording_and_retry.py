"""phase 3: recording metadata, waveform peaks, retry-one-question linkage

HAND-WRITTEN, same convention as the previous two migrations. Adds exactly what
docs/phase-3-BUILD.md's report/replay surface requires:

  - sessions.recording_key      (Task 3.3f/3.4d — the S3/MinIO object the report player
                                  streams; realtime writes this at finalize, api only reads it
                                  to mint a presigned URL — CLAUDE.md §2, api never touches
                                  audio bytes themselves)
  - sessions.recording_format   ("opus" | "wav" | NULL — NULL means nothing was ever recorded,
                                  a legitimate case for a session with zero turns, not an error)
  - sessions.peaks              (Task 3.3a — ~1000-bucket waveform peaks array, computed once
                                  server-side at finalize so the report never decodes audio
                                  client-side to draw a waveform)
  - sessions.retry_of_session_id / .retry_of_turn_id
                                  (Task 3.4f — "retry one question", linking the short follow-up
                                  session back to the turn it re-asks. `retry_of_turn_id` has no
                                  FK for the same reason turn_metrics.turn_id/turn_scores.turn_id
                                  don't: `turns` is partitioned and only `(id, created_at)`
                                  together is a real PK target — see docs/decisions/0002.)

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-08-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("recording_key", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("recording_format", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_sessions_recording_format",
        "sessions",
        "recording_format IS NULL OR recording_format IN ('wav', 'opus')",
    )
    op.add_column(
        "sessions",
        sa.Column("peaks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("sessions", sa.Column("retry_of_session_id", sa.UUID(), nullable=True))
    op.add_column("sessions", sa.Column("retry_of_turn_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_sessions_retry_of_session_id",
        "sessions",
        "sessions",
        ["retry_of_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sessions_retry_of_session_id", "sessions", ["retry_of_session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_retry_of_session_id", table_name="sessions")
    op.drop_constraint("fk_sessions_retry_of_session_id", "sessions", type_="foreignkey")
    op.drop_column("sessions", "retry_of_turn_id")
    op.drop_column("sessions", "retry_of_session_id")
    op.drop_column("sessions", "peaks")
    op.drop_constraint("ck_sessions_recording_format", "sessions", type_="check")
    op.drop_column("sessions", "recording_format")
    op.drop_column("sessions", "recording_key")
