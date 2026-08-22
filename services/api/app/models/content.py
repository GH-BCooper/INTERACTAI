from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..models.base import Base, TimestampMixin, UUIDPk, sql_in

PERSONA_ARCHETYPES = ("interviewer", "hiring_manager", "recruiter", "examiner", "skeptic")
PERSONA_TEMPERAMENTS = ("warm", "neutral", "blunt", "adversarial")
SCENARIO_FAMILIES = ("technical", "behavioural", "negotiation", "viva")
SCENARIO_DIFFICULTIES = ("gentle", "standard", "hard")


class Persona(UUIDPk, TimestampMixin, Base):
    """content/personas/*.yaml, seeded by scripts/seed.py — see docs/phase-0-BUILD.md TASK 0.6."""

    __tablename__ = "personas"
    __table_args__ = (
        CheckConstraint(sql_in("archetype", PERSONA_ARCHETYPES), name="ck_personas_archetype"),
        CheckConstraint(
            sql_in("temperament", PERSONA_TEMPERAMENTS), name="ck_personas_temperament"
        ),
    )

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    archetype: Mapped[str] = mapped_column(Text, nullable=False)
    temperament: Mapped[str] = mapped_column(Text, nullable=False)
    voice_id: Mapped[str] = mapped_column(Text, nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)


class Scenario(UUIDPk, TimestampMixin, Base):
    """content/scenarios/*.yaml. `difficulty` names which authored variant this row *is*;
    `difficulty_params` carries the full gentle/standard/hard behavioural lookup table so the
    persona engine can apply tier-specific behaviour regardless of which variant was opened
    (docs/phase-0-BUILD.md TASK 0.6, "difficulty must change behaviour, not wording").
    """

    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint(sql_in("family", SCENARIO_FAMILIES), name="ck_scenarios_family"),
        CheckConstraint(
            sql_in("difficulty", SCENARIO_DIFFICULTIES), name="ck_scenarios_difficulty"
        ),
        CheckConstraint("length(brief) >= 200", name="ck_scenarios_brief_min_length"),
    )

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    family: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    difficulty: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    opening_strategy: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty_params: Mapped[dict[str, dict[str, object]]] = mapped_column(JSONB, nullable=False)
    persona_id: Mapped[std_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("personas.id", ondelete="SET NULL")
    )
    rubric_id: Mapped[std_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rubrics.id", ondelete="SET NULL")
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    # pgvector — column reserved now, ivfflat index deferred until embeddings are actually
    # populated (Phase 1+/5). See docs/phase-0-BUILD.md TASK 0.4 indexes table.
    # embedding is added via raw DDL in the migration (Vector type needs the pgvector extension
    # loaded before SQLAlchemy can reflect it; see migration 0001).


class Rubric(UUIDPk, TimestampMixin, Base):
    __tablename__ = "rubrics"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(aggregation_policy) = 'object' AND aggregation_policy ? 'method'",
            name="ck_rubrics_aggregation_policy_has_method",
        ),
    )

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # docs/phase-2-BUILD.md TASK 2.5f: "The aggregation policy is stored on the rubric, not
    # hardcoded, because it is a rubric property and may change." See
    # services/coach/app/report/aggregation.py for the shape this is read as.
    aggregation_policy: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {"method": "mean_weighted_by_confidence", "min_turns_with_signal": 2},
    )

    # Async SQLAlchemy has no lazy loading — every caller must selectinload() this explicitly
    # or hit MissingGreenlet (docs/phase-0-LEARN.md §4.3).
    criteria: Mapped[list[RubricCriterion]] = relationship(
        back_populates="rubric",
        order_by="RubricCriterion.display_order",
        cascade="all, delete-orphan",
    )


class RubricCriterion(UUIDPk, TimestampMixin, Base):
    """`anchor_descriptors` maps scale point ("1".."5") -> written definition. Required and
    complete — enforced by a CHECK constraint, not just app-level validation, because the
    validator in scripts/validate_content.py only runs at seed time and this must hold for any
    insert path. See docs/phase-0-BUILD.md TASK 0.4 acceptance criteria.
    """

    __tablename__ = "rubric_criteria"
    __table_args__ = (
        UniqueConstraint("rubric_id", "key", name="uq_rubric_criteria_rubric_key"),
        CheckConstraint(
            "jsonb_typeof(anchor_descriptors) = 'object' "
            "AND anchor_descriptors ?& array['1','2','3','4','5']",
            name="ck_rubric_criteria_anchor_descriptors_complete",
        ),
    )

    rubric_id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anchor_descriptors: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)

    rubric: Mapped[Rubric] = relationship(back_populates="criteria")
