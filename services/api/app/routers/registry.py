"""docs/phase-5-BUILD.md TASK 5.5c — the model registry's admin surface. Promotion/rollback are
exactly as consequential as they sound (they change what scores every future session), so both
require `AdminUser`, same as /admin/annotate/*.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..core.deps import AdminUser, DbSession
from ..schemas.registry import ModelVersionOut, PromoteRequest, RollbackRequest
from ..services import model_registry_service

router = APIRouter(prefix="/admin/registry", tags=["admin-registry"])


@router.get("/{role}/active", response_model=ModelVersionOut | None)
async def get_active(role: str, admin: AdminUser, db: DbSession) -> ModelVersionOut | None:
    del admin
    active = await model_registry_service.get_active(db, role)
    return ModelVersionOut.model_validate(active) if active else None


@router.post("/promote", response_model=ModelVersionOut)
async def promote(admin: AdminUser, db: DbSession, body: PromoteRequest) -> ModelVersionOut:
    del admin
    promoted = await model_registry_service.promote(
        db, candidate_version_id=body.candidate_version_id
    )
    await db.commit()
    return ModelVersionOut.model_validate(promoted)


@router.post("/rollback", response_model=ModelVersionOut)
async def rollback(admin: AdminUser, db: DbSession, body: RollbackRequest) -> ModelVersionOut:
    del admin
    rolled_back = await model_registry_service.rollback(
        db, target_version_id=body.target_version_id
    )
    await db.commit()
    return ModelVersionOut.model_validate(rolled_back)
