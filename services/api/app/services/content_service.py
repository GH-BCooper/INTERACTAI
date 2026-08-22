from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Persona, Rubric, Scenario


async def list_scenarios(
    db: AsyncSession,
    *,
    family: str | None = None,
    difficulty: str | None = None,
    duration_minutes: int | None = None,
    tag: str | None = None,
) -> list[Scenario]:
    stmt = select(Scenario)
    if family is not None:
        stmt = stmt.where(Scenario.family == family)
    if difficulty is not None:
        stmt = stmt.where(Scenario.difficulty == difficulty)
    if duration_minutes is not None:
        stmt = stmt.where(Scenario.duration_minutes == duration_minutes)
    if tag is not None:
        stmt = stmt.where(Scenario.tags.contains([tag]))
    stmt = stmt.order_by(Scenario.family, Scenario.difficulty)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_scenario(db: AsyncSession, scenario_id: std_uuid.UUID) -> Scenario | None:
    return await db.get(Scenario, scenario_id)


async def list_personas(db: AsyncSession) -> list[Persona]:
    result = await db.execute(select(Persona).order_by(Persona.name))
    return list(result.scalars().all())


async def get_persona(db: AsyncSession, persona_id: std_uuid.UUID) -> Persona | None:
    return await db.get(Persona, persona_id)


async def list_rubrics(db: AsyncSession) -> list[Rubric]:
    result = await db.execute(
        select(Rubric).options(selectinload(Rubric.criteria)).order_by(Rubric.name)
    )
    return list(result.scalars().all())


async def get_rubric(db: AsyncSession, rubric_id: std_uuid.UUID) -> Rubric | None:
    result = await db.execute(
        select(Rubric).options(selectinload(Rubric.criteria)).where(Rubric.id == rubric_id)
    )
    return result.scalar_one_or_none()


async def get_rubric_by_slug(db: AsyncSession, slug: str) -> Rubric | None:
    result = await db.execute(
        select(Rubric).options(selectinload(Rubric.criteria)).where(Rubric.slug == slug)
    )
    return result.scalar_one_or_none()
