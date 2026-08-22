"""phase 2: coach v0 + persona state columns, failed_jobs table

HAND-WRITTEN, not autogenerate-and-commit-blind (same convention as the initial migration,
docs/phase-0-BUILD.md TASK 0.4 acceptance criteria). Adds exactly what docs/phase-2-BUILD.md's
tasks require and nothing speculative:

  - sessions.question_plan       (Task 2.3b — the persona's question plan, mutates over the
                                   session, unlike the frozen `brief`)
  - rubrics.aggregation_policy   (Task 2.5f — "stored on the rubric, not hardcoded")
  - reports.next_actions / .highlight_turn_id / .lowlight_turn_id / .low_sample_size
                                  (Task 2.5g)
  - session_scores.percentile_vs_self  (Task 2.5f)
  - turn_scores.rationale        (Task 2.5b's CriterionScore.rationale)
  - failed_jobs                  (Task 2.2d — a report that never generates must be visible)

Existing rows: `rubrics.aggregation_policy` is NOT NULL with a server default so the two
already-seeded rubrics (Phase 0) don't need a data migration — `scripts/seed.py`/content YAML
overwrite it with the authored policy on the next `make seed`, same idempotent-upsert path
every other content field already goes through.

Revision ID: b1c2d3e4f5a6
Revises: a06824b506ad
Create Date: 2026-08-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a06824b506ad"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_DEFAULT_AGGREGATION_POLICY = (
    '\'{"method": "mean_weighted_by_confidence", "min_turns_with_signal": 2}\'::jsonb'
)


def upgrade() -> None:
    op.add_column("sessions", sa.Column("question_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.add_column(
        "rubrics",
        sa.Column(
            "aggregation_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(_DEFAULT_AGGREGATION_POLICY),
        ),
    )
    op.create_check_constraint(
        "ck_rubrics_aggregation_policy_has_method",
        "rubrics",
        "jsonb_typeof(aggregation_policy) = 'object' AND aggregation_policy ? 'method'",
    )
    # Drop the server_default once existing rows are backfilled — new inserts go through the
    # ORM column default instead (matches the convention every other JSONB default in this repo
    # already follows; the server_default here exists only to satisfy NOT NULL on the ALTER).
    op.alter_column("rubrics", "aggregation_policy", server_default=None)

    op.add_column(
        "reports",
        sa.Column(
            "next_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("reports", "next_actions", server_default=None)
    op.add_column("reports", sa.Column("highlight_turn_id", sa.UUID(), nullable=True))
    op.add_column("reports", sa.Column("lowlight_turn_id", sa.UUID(), nullable=True))
    op.add_column(
        "reports",
        sa.Column("low_sample_size", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("reports", "low_sample_size", server_default=None)

    op.add_column("session_scores", sa.Column("percentile_vs_self", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_session_scores_percentile_range",
        "session_scores",
        "percentile_vs_self IS NULL OR percentile_vs_self BETWEEN 0 AND 1",
    )

    op.add_column("turn_scores", sa.Column("rationale", sa.Text(), nullable=True))

    op.create_table(
        "failed_jobs",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("turn_id", sa.UUID(), nullable=True),
        sa.Column("job_name", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("job_name IN ('score_turn', 'generate_report')", name="ck_failed_jobs_name"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_failed_jobs_session_id", "failed_jobs", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_failed_jobs_session_id", table_name="failed_jobs")
    op.drop_table("failed_jobs")
    op.drop_column("turn_scores", "rationale")
    op.drop_constraint("ck_session_scores_percentile_range", "session_scores", type_="check")
    op.drop_column("session_scores", "percentile_vs_self")
    op.drop_column("reports", "low_sample_size")
    op.drop_column("reports", "lowlight_turn_id")
    op.drop_column("reports", "highlight_turn_id")
    op.drop_column("reports", "next_actions")
    op.drop_constraint("ck_rubrics_aggregation_policy_has_method", "rubrics", type_="check")
    op.drop_column("rubrics", "aggregation_policy")
    op.drop_column("sessions", "question_plan")
