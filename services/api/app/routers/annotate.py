"""docs/phase-5-BUILD.md TASK 5.3 — /admin/annotate/*. Every route requires `AdminUser`
(core/deps.py) — the FastAPI dependency raises `ForbiddenError` (403) before any handler body
runs for a non-admin caller, so "admin only" is enforced once, not re-checked per handler.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ..core.deps import AdminUser, DbSession
from ..schemas.annotate import (
    AnnotationProgress,
    AnnotationQueueItem,
    AnnotationSubmit,
    AnnotationSubmitOut,
)
from ..services import annotate_service

router = APIRouter(prefix="/admin/annotate", tags=["admin-annotate"])


@router.get("/queue", response_model=list[AnnotationQueueItem])
async def get_queue(
    admin: AdminUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    pre_labelled: bool = False,
) -> list[AnnotationQueueItem]:
    return await annotate_service.get_queue(db, admin, limit=limit, pre_labelled=pre_labelled)


@router.post("/submit", response_model=AnnotationSubmitOut, status_code=201)
async def submit(admin: AdminUser, db: DbSession, body: AnnotationSubmit) -> AnnotationSubmitOut:
    annotation = await annotate_service.submit_annotation(db, admin, body)
    await db.commit()
    return AnnotationSubmitOut.model_validate(annotation)


@router.get("/progress", response_model=AnnotationProgress)
async def get_progress(admin: AdminUser, db: DbSession) -> AnnotationProgress:
    return await annotate_service.get_progress(db)
