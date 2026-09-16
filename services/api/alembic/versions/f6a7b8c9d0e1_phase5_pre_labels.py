"""phase 5: pre_labels table (Task 5.3d — model suggestions for the training split only)

HAND-WRITTEN, same convention as the previous five migrations. A separate migration from
e5f6a7b8c9d0 because this table was designed slightly later, once the annotation queue's actual
read path made clear that a suggestion (unreviewed, no NOT-NULL score guarantee needed on the
*human* side) shouldn't live in the `annotations` table itself.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-24 01:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "pre_labels",
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
        sa.Column("turn_id", sa.UUID(), nullable=False),
        sa.Column("criterion_key", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_pre_labels_score_range"),
        sa.UniqueConstraint("turn_id", "criterion_key", name="uq_pre_labels_turn_criterion"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pre_labels")
