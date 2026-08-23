"""phase 4: onboarding/audio profile fields, privacy settings, consent, BYOK, training exclusion

HAND-WRITTEN, same convention as the previous three migrations. Adds exactly what
docs/phase-4-BUILD.md's tasks require:

  - profiles.goal / .experience_level / .focus_areas   (Task 4.3 — onboarding steps 1/2)
  - profiles.captions_default / .speaking_rate / .noise_suppression / .echo_cancellation
                                                         (Task 4.4 — Settings > Audio)
  - users.training_consent / .audio_retention_days      (Task 4.4/4.5 — Settings > Privacy;
                                                           AS-03/AS-04)
  - users.prefer_local_models                           (Task 4.4 — Settings > Models)
  - users.onboarded_at                                  (Task 4.3 — "user already onboarded"
                                                           edge case)
  - turns.training_excluded                             (Task 4.5a — consent-revocation cascade)
  - turns.text_scrubbed                                 (Task 4.5b — PII-scrubbed transcript,
                                                           written once by services/coach's
                                                           generate_report job, alongside the
                                                           unscrubbed original every other report
                                                           surface still reads)
  - consents table                                       (Task 4.5a — per-session consent record)
  - provider_credentials table                          (Task 4.4 — BYOK, encrypted at rest)
  - sessions.report_viewed_at                           (Task 4.1 — dashboard attention panel's
                                                           "an unread report" needs a read marker
                                                           that didn't previously exist; set by
                                                           GET /sessions/{id}/report as a side
                                                           effect of the report actually loading)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-23 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # ── profiles: onboarding + audio settings ────────────────────────────────────────────────
    op.add_column("profiles", sa.Column("goal", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_profiles_goal",
        "profiles",
        "goal IS NULL OR goal IN ('job_interview', 'technical_interview', 'salary_negotiation')",
    )
    op.add_column("profiles", sa.Column("experience_level", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_profiles_experience_level",
        "profiles",
        "experience_level IS NULL OR experience_level IN "
        "('student', 'early_career', 'mid_level', 'senior', 'staff_plus')",
    )
    op.add_column(
        "profiles",
        sa.Column(
            "focus_areas", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    op.alter_column("profiles", "focus_areas", server_default=None)
    op.add_column(
        "profiles",
        sa.Column("captions_default", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("profiles", "captions_default", server_default=None)
    op.add_column(
        "profiles",
        sa.Column("speaking_rate", sa.Float(), nullable=False, server_default=sa.text("1.0")),
    )
    op.alter_column("profiles", "speaking_rate", server_default=None)
    op.create_check_constraint(
        "ck_profiles_speaking_rate_range", "profiles", "speaking_rate BETWEEN 0.5 AND 2.0"
    )
    op.add_column(
        "profiles",
        sa.Column("noise_suppression", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("profiles", "noise_suppression", server_default=None)
    op.add_column(
        "profiles",
        sa.Column("echo_cancellation", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("profiles", "echo_cancellation", server_default=None)

    # ── users: privacy + models settings + onboarding marker ────────────────────────────────
    op.add_column(
        "users",
        sa.Column("training_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "training_consent", server_default=None)
    op.add_column(
        "users",
        sa.Column(
            "audio_retention_days", sa.Integer(), nullable=False, server_default=sa.text("30")
        ),
    )
    op.alter_column("users", "audio_retention_days", server_default=None)
    op.create_check_constraint(
        "ck_users_audio_retention_days_range", "users", "audio_retention_days BETWEEN 0 AND 365"
    )
    op.add_column(
        "users",
        sa.Column("prefer_local_models", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "prefer_local_models", server_default=None)
    op.add_column("users", sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True))

    # ── turns: training-consent-revocation cascade target ────────────────────────────────────
    op.add_column(
        "turns",
        sa.Column("training_excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("turns", "training_excluded", server_default=None)
    op.add_column("turns", sa.Column("text_scrubbed", sa.Text(), nullable=True))

    # ── consents: one row per session (Task 4.5a) ─────────────────────────────────────────────
    op.create_table(
        "consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("recording_consent", sa.Boolean(), nullable=False),
        sa.Column("training_consent", sa.Boolean(), nullable=False),
        sa.Column("consent_version", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_consents_session_id"),
    )

    # ── provider_credentials: BYOK (Task 4.4) ─────────────────────────────────────────────────
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("last_test_status", sa.Text(), nullable=False, server_default="untested"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('groq')", name="ck_provider_credentials_provider"),
        sa.CheckConstraint(
            "last_test_status IN ('untested', 'success', 'failed')",
            name="ck_provider_credentials_last_test_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_provider_credentials_user_provider"),
    )
    op.alter_column("provider_credentials", "last_test_status", server_default=None)
    op.create_index(
        "ix_provider_credentials_user_id", "provider_credentials", ["user_id"], unique=False
    )

    # ── sessions: report-read marker (Task 4.1) ───────────────────────────────────────────────
    op.add_column("sessions", sa.Column("report_viewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "report_viewed_at")

    op.drop_index("ix_provider_credentials_user_id", table_name="provider_credentials")
    op.drop_table("provider_credentials")
    op.drop_table("consents")

    op.drop_column("turns", "text_scrubbed")
    op.drop_column("turns", "training_excluded")

    op.drop_column("users", "onboarded_at")
    op.drop_column("users", "prefer_local_models")
    op.drop_constraint("ck_users_audio_retention_days_range", "users", type_="check")
    op.drop_column("users", "audio_retention_days")
    op.drop_column("users", "training_consent")

    op.drop_column("profiles", "echo_cancellation")
    op.drop_column("profiles", "noise_suppression")
    op.drop_constraint("ck_profiles_speaking_rate_range", "profiles", type_="check")
    op.drop_column("profiles", "speaking_rate")
    op.drop_column("profiles", "captions_default")
    op.drop_column("profiles", "focus_areas")
    op.drop_constraint("ck_profiles_experience_level", "profiles", type_="check")
    op.drop_column("profiles", "experience_level")
    op.drop_constraint("ck_profiles_goal", "profiles", type_="check")
    op.drop_column("profiles", "goal")
