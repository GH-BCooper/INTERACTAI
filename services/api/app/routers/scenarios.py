from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from ..core.deps import DbSession
from ..core.exceptions import NotFoundError
from ..schemas.content import ScenarioOut
from ..services import content_service

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioOut])
async def list_scenarios(
    db: DbSession,
    family: Annotated[str | None, Query()] = None,
    difficulty: Annotated[str | None, Query()] = None,
    duration: Annotated[int | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
) -> list[ScenarioOut]:
    scenarios = await content_service.list_scenarios(
        db, family=family, difficulty=difficulty, duration_minutes=duration, tag=tag
    )
    return [ScenarioOut.model_validate(s) for s in scenarios]


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(scenario_id: UUID, db: DbSession) -> ScenarioOut:
    scenario = await content_service.get_scenario(db, scenario_id)
    if scenario is None:
        raise NotFoundError("Scenario not found.")
    return ScenarioOut.model_validate(scenario)


@router.post("", status_code=501)
async def create_scenario() -> dict[str, str]:
    """P1 — authoring UI. Content is authored as YAML in content/scenarios/ and seeded via
    `make seed` for now (docs/phase-0-BUILD.md TASK 0.5).
    """
    return {
        "detail": "Not implemented yet — content is authored via content/scenarios/ + make seed"
    }
