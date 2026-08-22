#!/usr/bin/env python3
"""Loads content/{personas,rubrics,scenarios}/*.yaml into the database.

Idempotent by slug (personas, rubrics, scenarios) and by (rubric_id, key) for rubric
criteria: re-running updates existing rows in place via `ON CONFLICT ... DO UPDATE`, never
duplicates. Refuses to write anything if scripts/validate_content.py finds a problem.

Usage: uv run python scripts/seed.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"
API_DIR = REPO_ROOT / "services" / "api"
# REPO_ROOT (not just API_DIR) on sys.path so `scripts.validate_content` resolves the same way
# whether this file runs standalone (`uv run python scripts/seed.py`) or is imported as
# `scripts.seed` (tests/integration/conftest.py's seeded_content fixture).
for _path in (str(REPO_ROOT), str(API_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.core.config import get_settings  # noqa: E402
from app.models import Persona, Rubric, RubricCriterion, Scenario  # noqa: E402
from scripts.validate_content import validate_all  # noqa: E402


def _load_yaml(subdir: str) -> list[dict]:
    directory = CONTENT_DIR / subdir
    return [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.yaml"))
    ]


async def _upsert_personas(db: AsyncSession, personas: list[dict]) -> dict[str, object]:
    slug_to_id: dict[str, object] = {}
    for p in personas:
        stmt = insert(Persona).values(
            slug=p["slug"],
            name=p["name"],
            archetype=p["archetype"],
            temperament=p["temperament"],
            voice_id=p["voice_id"],
            brief=p["brief"],
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Persona.slug],
            set_={
                "name": stmt.excluded.name,
                "archetype": stmt.excluded.archetype,
                "temperament": stmt.excluded.temperament,
                "voice_id": stmt.excluded.voice_id,
                "brief": stmt.excluded.brief,
            },
        ).returning(Persona.id)
        result = await db.execute(stmt)
        slug_to_id[p["slug"]] = result.scalar_one()
    return slug_to_id


async def _upsert_rubrics(db: AsyncSession, rubrics: list[dict]) -> dict[str, object]:
    slug_to_id: dict[str, object] = {}
    for r in rubrics:
        stmt = insert(Rubric).values(
            slug=r["slug"],
            name=r["name"],
            description=r["description"],
            aggregation_policy=r["aggregation_policy"],
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Rubric.slug],
            set_={
                "name": stmt.excluded.name,
                "description": stmt.excluded.description,
                "aggregation_policy": stmt.excluded.aggregation_policy,
            },
        ).returning(Rubric.id)
        result = await db.execute(stmt)
        rubric_id = result.scalar_one()
        slug_to_id[r["slug"]] = rubric_id

        for order, criterion in enumerate(r["criteria"]):
            c_stmt = insert(RubricCriterion).values(
                rubric_id=rubric_id,
                key=criterion["key"],
                name=criterion.get("name", criterion["key"]),
                description=criterion.get("description", ""),
                display_order=order,
                anchor_descriptors=criterion["anchor_descriptors"],
            )
            c_stmt = c_stmt.on_conflict_do_update(
                index_elements=[RubricCriterion.rubric_id, RubricCriterion.key],
                set_={
                    "name": c_stmt.excluded.name,
                    "description": c_stmt.excluded.description,
                    "display_order": c_stmt.excluded.display_order,
                    "anchor_descriptors": c_stmt.excluded.anchor_descriptors,
                },
            )
            await db.execute(c_stmt)
    return slug_to_id


async def _upsert_scenarios(
    db: AsyncSession,
    scenarios: list[dict],
    persona_ids: dict[str, object],
    rubric_ids: dict[str, object],
) -> None:
    for s in scenarios:
        stmt = insert(Scenario).values(
            slug=s["slug"],
            family=s["family"],
            difficulty=s["difficulty"],
            title=s["title"],
            brief=s["brief"],
            opening_strategy=s["opening_strategy"],
            difficulty_params=s["difficulty_params"],
            persona_id=persona_ids.get(s.get("persona_slug", "")),
            rubric_id=rubric_ids.get(s.get("rubric_slug", "")),
            duration_minutes=s.get("duration_minutes", 15),
            tags=s.get("tags", []),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Scenario.slug],
            set_={
                "family": stmt.excluded.family,
                "difficulty": stmt.excluded.difficulty,
                "title": stmt.excluded.title,
                "brief": stmt.excluded.brief,
                "opening_strategy": stmt.excluded.opening_strategy,
                "difficulty_params": stmt.excluded.difficulty_params,
                "persona_id": stmt.excluded.persona_id,
                "rubric_id": stmt.excluded.rubric_id,
                "duration_minutes": stmt.excluded.duration_minutes,
                "tags": stmt.excluded.tags,
            },
        )
        await db.execute(stmt)


async def seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            personas = _load_yaml("personas")
            rubrics = _load_yaml("rubrics")
            scenarios = _load_yaml("scenarios")

            persona_ids = await _upsert_personas(db, personas)
            rubric_ids = await _upsert_rubrics(db, rubrics)
            await _upsert_scenarios(db, scenarios, persona_ids, rubric_ids)

            await db.commit()

            print(
                f"seeded {len(personas)} personas, {len(rubrics)} rubrics, "
                f"{len(scenarios)} scenarios."
            )

            counts = {}
            models_by_label = [
                ("personas", Persona),
                ("rubrics", Rubric),
                ("scenarios", Scenario),
            ]
            for label, model in models_by_label:
                result = await db.execute(select(model))
                counts[label] = len(result.scalars().all())
            print(f"row counts now: {counts}")
    finally:
        await engine.dispose()


def main() -> int:
    errors = validate_all()
    if errors:
        print(f"content validation FAILED - {len(errors)} error(s), not seeding:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    asyncio.run(seed())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
