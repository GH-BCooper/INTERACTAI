from __future__ import annotations

from fastapi import APIRouter

from ..core.deps import DbSession
from ..schemas.content import PersonaOut
from ..services import content_service

router = APIRouter(prefix="/personas", tags=["personas"])


@router.get("", response_model=list[PersonaOut])
async def list_personas(db: DbSession) -> list[PersonaOut]:
    personas = await content_service.list_personas(db)
    return [PersonaOut.model_validate(p) for p in personas]
