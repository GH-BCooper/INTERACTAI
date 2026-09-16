"""phase 6: host_class on latency_events, suite metrics on eval_runs, deployment markers

HAND-WRITTEN, same convention as every previous migration.

- `latency_events.host_class` — TASK 6.1a "filterable by host class". Nullable: every row written
  before this migration has no recorded host, and inventing one would be a fabricated fact.
- `ix_latency_events_stage_created_at_cover` — (stage, created_at) INCLUDE (duration_ms,
  session_id, turn_id, host_class): the e2e percentile query is then an index-only scan
  (TASK 6.1 "page loads in < 2 s over 10,000 latency events, indexes verified with EXPLAIN").
- `model_calls` (created_at) index for the global, newest-first model call table.
- `eval_runs.metrics` / `eval_runs.host_class` — Level 1 (speech) and Level 2 (persona) suites
  report WER, RTF, endpoint precision/recall, character-break rate, etc. None of those are kappa
  columns; they live in one JSONB bag keyed by metric name.
- `turns.training_excluded` server default `false` (see upgrade()).
- `deployment_events` — TASK 6.2 "regression chart with deployment markers". Written by the
  model registry on every promotion/rollback, and by `scripts/record_deployment.py` for prompt
  and service deploys.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-17 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

DEPLOYMENT_KINDS = ("model_promoted", "model_rolled_back", "prompt_version", "service_deploy")


def upgrade() -> None:
    # Defence in depth for the Phase 4 regression realtime hit (NOT NULL, no default): a writer
    # that omits the column now gets `false`, which is the correct consent-neutral value.
    op.alter_column("turns", "training_excluded", server_default=sa.false())
    op.add_column("latency_events", sa.Column("host_class", sa.Text(), nullable=True))
    op.create_index(
        "ix_latency_events_stage_created_at_cover",
        "latency_events",
        ["stage", "created_at"],
        postgresql_include=["duration_ms", "session_id", "turn_id", "host_class"],
    )
    op.drop_index("ix_latency_events_stage_created_at", table_name="latency_events")
    op.create_index("ix_model_calls_created_at", "model_calls", ["created_at"])

    op.add_column(
        "eval_runs",
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("eval_runs", sa.Column("host_class", sa.Text(), nullable=True))
    op.create_index("ix_eval_runs_suite_created_at", "eval_runs", ["suite", "created_at"])

    kinds = ", ".join(f"'{k}'" for k in DEPLOYMENT_KINDS)
    op.create_table(
        "deployment_events",
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
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(f"kind IN ({kinds})", name="ck_deployment_events_kind"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployment_events_created_at", "deployment_events", ["created_at"])


def downgrade() -> None:
    op.alter_column("turns", "training_excluded", server_default=None)
    op.drop_index("ix_deployment_events_created_at", table_name="deployment_events")
    op.drop_table("deployment_events")
    op.drop_index("ix_eval_runs_suite_created_at", table_name="eval_runs")
    op.drop_column("eval_runs", "host_class")
    op.drop_column("eval_runs", "metrics")
    op.drop_index("ix_model_calls_created_at", table_name="model_calls")
    op.create_index("ix_latency_events_stage_created_at", "latency_events", ["stage", "created_at"])
    op.drop_index("ix_latency_events_stage_created_at_cover", table_name="latency_events")
    op.drop_column("latency_events", "host_class")
