from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from ..core.deps import DbSession
from ..core.exceptions import NotFoundError
from ..schemas.content import RubricOut
from ..services import content_service

router = APIRouter(prefix="/rubrics", tags=["rubrics"])


@router.get("", response_model=list[RubricOut])
async def list_rubrics(db: DbSession) -> list[RubricOut]:
    rubrics = await content_service.list_rubrics(db)
    return [RubricOut.model_validate(r) for r in rubrics]


@router.get("/{rubric_id}", response_model=RubricOut)
async def get_rubric(rubric_id: UUID, db: DbSession) -> RubricOut:
    rubric = await content_service.get_rubric(db, rubric_id)
    if rubric is None:
        raise NotFoundError("Rubric not found.")
    return RubricOut.model_validate(rubric)
