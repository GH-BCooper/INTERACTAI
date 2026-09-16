"""phase 5: shadow_scores table (Task 5.5d — CS-12 shadow mode)

HAND-WRITTEN. See services/api/app/models/shadow_score.py's docstring and
docs/decisions/0021-shadow-scores-separate-table.md for why this is a new table rather than
widening `turn_scores`'s unique constraint.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-24 02:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "shadow_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("turn_id", sa.UUID(), nullable=False),
        sa.Column("criterion_key", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 1 AND 5", name="ck_shadow_scores_score_range"
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="ck_shadow_scores_confidence_range"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "turn_id", "criterion_key", "model_version",
            name="uq_shadow_scores_turn_criterion_model",
        ),
    )
    op.create_index("ix_shadow_scores_turn_id", "shadow_scores", ["turn_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shadow_scores_turn_id", table_name="shadow_scores")
    op.drop_table("shadow_scores")
