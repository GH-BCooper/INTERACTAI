"""phase 5: dataset revisions, model registry, eval runs, annotation pre-labelling, admin flag

HAND-WRITTEN, same convention as the previous four migrations. Adds exactly what
docs/phase-5-BUILD.md TASK 5.1 requires, plus the small amount of plumbing that task needs but
doesn't itself name:

  - dataset_revisions table                 (TASK 5.1/5.2d — one row per reproducible build)
  - dataset_members table                   (not in the task's own table list — per-turn split/
                                              source/double-labeled assignment for one revision;
                                              see services/api/app/models/training.py's docstring
                                              for why this isn't a column on `turns` itself)
  - model_versions table + partial unique index on (role) WHERE status='active'
                                              (TASK 5.1's own acceptance criterion, enforced here
                                              as a constraint, not application logic)
  - eval_runs table, dataset_revision_hash NOT NULL
                                              (TASK 5.1's own acceptance criterion: "a row
                                              without one is rejected")
  - annotations.pre_labelled / .pre_label_score
                                              (TASK 5.3d — correction-rate tracking)
  - users.is_admin                          (TASK 5.3a — "/app/annotate (admin only)"; no role
                                              system exists anywhere else in this project, see
                                              docs/decisions/0019)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-24 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # ── users: admin flag (Task 5.3a) ─────────────────────────────────────────────────────────
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.alter_column("users", "is_admin", server_default=None)

    # ── annotations: pre-labelling correction-rate tracking (Task 5.3d) ──────────────────────
    op.add_column(
        "annotations",
        sa.Column("pre_labelled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("annotations", "pre_labelled", server_default=None)
    op.add_column("annotations", sa.Column("pre_label_score", sa.Integer(), nullable=True))

    # ── dataset_revisions: one row per reproducible build (Task 5.1/5.2d) ────────────────────
    op.create_table(
        "dataset_revisions",
        sa.Column("hash", sa.Text(), nullable=False),
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
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("label_count", sa.Integer(), nullable=False),
        sa.Column("speaker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("split_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excluded_turn_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("turn_count >= 0", name="ck_dataset_revisions_turn_count_nonneg"),
        sa.CheckConstraint("label_count >= 0", name="ck_dataset_revisions_label_count_nonneg"),
        sa.PrimaryKeyConstraint("hash"),
    )
    op.alter_column("dataset_revisions", "speaker_count", server_default=None)

    # ── dataset_members: per-turn assignment within one revision ─────────────────────────────
    op.create_table(
        "dataset_members",
        sa.Column("dataset_revision_hash", sa.Text(), nullable=False),
        sa.Column("turn_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("speaker_key", sa.Text(), nullable=False),
        sa.Column("split", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("double_labeled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("synthetic_quality_level", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "split IN ('train', 'validation', 'test')", name="ck_dataset_members_split"
        ),
        sa.CheckConstraint(
            "source IN ('self', 'recruited', 'synthetic')", name="ck_dataset_members_source"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_revision_hash"], ["dataset_revisions.hash"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("dataset_revision_hash", "turn_id"),
    )
    op.alter_column("dataset_members", "double_labeled", server_default=None)
    op.create_index(
        "ix_dataset_members_speaker_key", "dataset_members", ["speaker_key"], unique=False
    )
    op.create_index(
        "ix_dataset_members_revision_split",
        "dataset_members",
        ["dataset_revision_hash", "split"],
        unique=False,
    )

    # ── model_versions: the registry (Task 5.1/5.5c) ──────────────────────────────────────────
    op.create_table(
        "model_versions",
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
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_model", sa.Text(), nullable=False),
        sa.Column("adapter_key", sa.Text(), nullable=True),
        sa.Column("trained_on_dataset", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="training"),
        sa.Column("seed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dataset_revision_hash", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('training', 'candidate', 'active', 'retired')",
            name="ck_model_versions_status",
        ),
        sa.CheckConstraint("seed_count >= 0", name="ck_model_versions_seed_count_nonneg"),
        sa.ForeignKeyConstraint(
            ["dataset_revision_hash"], ["dataset_revisions.hash"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("model_versions", "status", server_default=None)
    op.alter_column("model_versions", "seed_count", server_default=None)
    op.create_index("ix_model_versions_role", "model_versions", ["role"], unique=False)
    # TASK 5.1's own acceptance criterion: "exactly one model_versions row per role may have
    # status='active'... Enforce with a partial unique index — not application logic."
    op.create_index(
        "uq_model_versions_one_active_per_role",
        "model_versions",
        ["role"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # ── eval_runs (Task 5.1/5.5a) ──────────────────────────────────────────────────────────────
    op.create_table(
        "eval_runs",
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
        sa.Column("suite", sa.Text(), nullable=False),
        sa.Column("configuration", sa.Text(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("qwk", sa.Float(), nullable=True),
        sa.Column("mae", sa.Float(), nullable=True),
        sa.Column("spearman", sa.Float(), nullable=True),
        sa.Column("adjacent_accuracy", sa.Float(), nullable=True),
        sa.Column("ece", sa.Float(), nullable=True),
        sa.Column("false_alarm_rate", sa.Float(), nullable=True),
        sa.Column("mean_cost_cents", sa.Float(), nullable=True),
        sa.Column("mean_latency_ms", sa.Float(), nullable=True),
        sa.Column("per_criterion", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        # NOT NULL, no server default — TASK 5.1's own acceptance criterion: "a row without one
        # is rejected." An INSERT that omits it fails at the database, not just in application
        # code that might be bypassed by a future direct-SQL script.
        sa.Column("dataset_revision_hash", sa.Text(), nullable=False),
        sa.Column("split", sa.Text(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("split IN ('validation', 'test')", name="ck_eval_runs_split"),
        sa.CheckConstraint(
            "qwk IS NULL OR qwk BETWEEN -1 AND 1", name="ck_eval_runs_qwk_range"
        ),
        sa.CheckConstraint("ece IS NULL OR ece BETWEEN 0 AND 1", name="ck_eval_runs_ece_range"),
        sa.CheckConstraint(
            "adjacent_accuracy IS NULL OR adjacent_accuracy BETWEEN 0 AND 1",
            name="ck_eval_runs_adjacent_accuracy_range",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"], ["model_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_revision_hash"], ["dataset_revisions.hash"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("eval_runs", "published", server_default=None)
    op.create_index(
        "ix_eval_runs_configuration", "eval_runs", ["configuration"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_eval_runs_configuration", table_name="eval_runs")
    op.drop_table("eval_runs")

    op.drop_index("uq_model_versions_one_active_per_role", table_name="model_versions")
    op.drop_index("ix_model_versions_role", table_name="model_versions")
    op.drop_table("model_versions")

    op.drop_index("ix_dataset_members_revision_split", table_name="dataset_members")
    op.drop_index("ix_dataset_members_speaker_key", table_name="dataset_members")
    op.drop_table("dataset_members")

    op.drop_table("dataset_revisions")

    op.drop_column("annotations", "pre_label_score")
    op.drop_column("annotations", "pre_labelled")

    op.drop_column("users", "is_admin")
