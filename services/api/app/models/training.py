from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..models.base import Base, TimestampMixin, UUIDPk, sql_in

MODEL_VERSION_STATUSES = ("training", "candidate", "active", "retired")
EVAL_RUN_SPLITS = ("validation", "test")
DATASET_SOURCES = ("self", "recruited", "synthetic")
DATASET_SPLITS = ("train", "validation", "test")


class DatasetRevision(TimestampMixin, Base):
    """docs/phase-5-BUILD.md TASK 5.1/5.2d. `hash` is a content hash over
    `(turn_ids, label_ids, split assignment)` — the primary key, not a surrogate UUID, because
    the hash *is* the identity: two builds that hash the same are the same dataset, and every
    training run / eval run records this string directly so a metric is always attributable to
    an exact set of turns and labels (CLAUDE.md §10, "never fabricate a metric" extends to
    "never report a metric with no way to reproduce it").
    """

    __tablename__ = "dataset_revisions"
    __table_args__ = (
        CheckConstraint("turn_count >= 0", name="ck_dataset_revisions_turn_count_nonneg"),
        CheckConstraint("label_count >= 0", name="ck_dataset_revisions_label_count_nonneg"),
    )

    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False)
    label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # {"self": n, "recruited": n, "synthetic": n} — Task 5.2a's per-source tag, tallied.
    source_breakdown: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    # {"train": n, "validation": n, "test": n} — Task 5.2c's 70/15/15 target, as measured.
    split_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    # Task 5.2a: "the exclusion is recorded in dataset_revisions.excluded_turn_ids" — turn ids
    # (as strings; turns is partitioned, see docs/decisions/0002) filtered out because
    # training_excluded=true at build time.
    excluded_turn_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text)


class DatasetMember(Base):
    """Not in the phase doc's own table list — necessary plumbing it doesn't spell out. A given
    turn's split/source assignment is a property of *one dataset revision*, not of the turn
    itself (the same turn could be assigned differently across rebuilds, e.g. once stratification
    can finally use real labels) — so this is its own table keyed by (dataset_revision_hash,
    turn_id) rather than a column bolted onto the hot, partitioned `turns` table.
    `speaker_key` is `sessions.user_id` as text (or a synthetic-batch id for `source=synthetic`
    turns, which have no real speaker) — the field the leakage assertion (Task 5.2c) actually
    checks. `double_labeled` marks membership in the 200-turn IAA subset (Task 5.3c).
    """

    __tablename__ = "dataset_members"
    __table_args__ = (
        CheckConstraint(sql_in("split", DATASET_SPLITS), name="ck_dataset_members_split"),
        CheckConstraint(sql_in("source", DATASET_SOURCES), name="ck_dataset_members_source"),
    )

    dataset_revision_hash: Mapped[str] = mapped_column(
        Text, ForeignKey("dataset_revisions.hash", ondelete="CASCADE"), primary_key=True
    )
    turn_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[std_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    speaker_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    split: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    double_labeled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Task 5.2b: the generation parameter for synthetic turns (1-5), NULL for real turns.
    # "The instructed level is a generation parameter, not a label" — never copied into a score.
    synthetic_quality_level: Mapped[int | None] = mapped_column(Integer)


class ModelVersion(UUIDPk, TimestampMixin, Base):
    """docs/phase-5-BUILD.md TASK 5.1/5.5c. Exactly one row per `role` may have
    `status='active'` — enforced by a partial unique index in the migration, not application
    logic (the task's own acceptance criterion), so a promotion race can't ever leave two active
    scorers for the realtime/coach services to disagree about which to load.
    """

    __tablename__ = "model_versions"
    __table_args__ = (
        CheckConstraint(sql_in("status", MODEL_VERSION_STATUSES), name="ck_model_versions_status"),
        CheckConstraint("seed_count >= 0", name="ck_model_versions_seed_count_nonneg"),
    )

    role: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_model: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_key: Mapped[str | None] = mapped_column(Text)
    # Free-text description of what it was trained on (e.g. "1,240 turns, rev a1b2c3..d4");
    # dataset_revision_hash below is the machine-checkable version of the same fact.
    trained_on_dataset: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="training")
    seed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dataset_revision_hash: Mapped[str | None] = mapped_column(
        Text, ForeignKey("dataset_revisions.hash", ondelete="SET NULL")
    )


class EvalRun(UUIDPk, TimestampMixin, Base):
    """docs/phase-5-BUILD.md TASK 5.1/5.5a. `configuration` names which ablation-ladder row this
    is (docs/phase-5-BUILD.md TASK 5.4's rows 1-8, e.g. "majority_class",
    "frontier_few_shot", "finetuned_ensemble_calibrated") so `docs/RESULTS.md` can be generated
    by grouping this table, not hand-assembled. `dataset_revision_hash` is NOT NULL — Task 5.1's
    own acceptance criterion: "a row without one is rejected."
    """

    __tablename__ = "eval_runs"
    __table_args__ = (
        CheckConstraint(sql_in("split", EVAL_RUN_SPLITS), name="ck_eval_runs_split"),
        CheckConstraint(
            "qwk IS NULL OR qwk BETWEEN -1 AND 1", name="ck_eval_runs_qwk_range"
        ),
        CheckConstraint(
            "ece IS NULL OR ece BETWEEN 0 AND 1", name="ck_eval_runs_ece_range"
        ),
        CheckConstraint(
            "adjacent_accuracy IS NULL OR adjacent_accuracy BETWEEN 0 AND 1",
            name="ck_eval_runs_adjacent_accuracy_range",
        ),
    )

    suite: Mapped[str] = mapped_column(Text, nullable=False)
    configuration: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    model_version_id: Mapped[std_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    prompt_version: Mapped[str | None] = mapped_column(Text)
    qwk: Mapped[float | None] = mapped_column(Float)
    mae: Mapped[float | None] = mapped_column(Float)
    spearman: Mapped[float | None] = mapped_column(Float)
    adjacent_accuracy: Mapped[float | None] = mapped_column(Float)
    ece: Mapped[float | None] = mapped_column(Float)
    false_alarm_rate: Mapped[float | None] = mapped_column(Float)
    mean_cost_cents: Mapped[float | None] = mapped_column(Float)
    mean_latency_ms: Mapped[float | None] = mapped_column(Float)
    # Per-criterion breakdown, {"structure": {"qwk": .., "mae": ..}, ...} — Task 5.5a's "always
    # reported beside the human ceiling" needs the same shape for both model rows and the
    # human-ceiling row computed in Task 5.3c.
    per_criterion: Mapped[dict[str, dict[str, float]]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    seed: Mapped[int | None] = mapped_column(Integer)
    dataset_revision_hash: Mapped[str] = mapped_column(
        Text, ForeignKey("dataset_revisions.hash", ondelete="RESTRICT"), nullable=False
    )
    split: Mapped[str] = mapped_column(Text, nullable=False)
    # Task 5.5b: "The harness must refuse to evaluate on the reporting split unless explicitly
    # flagged --publish, and it logs every such access." True the moment this row came from a
    # --publish invocation touching the reporting (test) split.
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
