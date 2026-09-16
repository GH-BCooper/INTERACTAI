"""Phase 6 TASK 6.1 (`/app/observability`) and TASK 6.2 (`/app/evals`) — admin-only read
surfaces. Promotion and rollback stay on `/admin/registry/*` (routers/registry.py); this router
only adds the registry *listing* the evaluations page needs."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from ..core.deps import AdminUser, DbSession
from ..core.exceptions import NotFoundError
from ..core.security import REPLAY_TOKEN_TTL_SECONDS, mint_replay_token
from ..models import Session
from ..schemas.session import ReplayTokenOut
from ..services import evals_service, observability_service

router = APIRouter(prefix="/admin", tags=["admin-observability"])

Days = Query(7, ge=1, le=365)


@router.get("/observability/latency")
async def latency(
    admin: AdminUser,
    db: DbSession,
    days: int = Days,
    family: str | None = None,
    host_class: str | None = None,
) -> dict[str, Any]:
    del admin
    return await observability_service.latency_header(
        db, days=days, family=family, host_class=host_class
    )


@router.get("/observability/stages")
async def stages(
    admin: AdminUser,
    db: DbSession,
    days: int = Days,
    family: str | None = None,
    host_class: str | None = None,
) -> list[dict[str, Any]]:
    del admin
    return await observability_service.stage_breakdown(
        db, days=days, family=family, host_class=host_class
    )


@router.get("/observability/turns")
async def turns(
    admin: AdminUser, db: DbSession, limit: int = Query(50, ge=1, le=500)
) -> list[dict[str, Any]]:
    del admin
    return await observability_service.recent_turns(db, limit=limit)


@router.get("/observability/turns/{turn_id}")
async def turn_waterfall(turn_id: UUID, admin: AdminUser, db: DbSession) -> dict[str, Any]:
    del admin
    return await observability_service.turn_waterfall(db, turn_id)


@router.post("/observability/sessions/{session_id}/replay-token", response_model=ReplayTokenOut)
async def admin_replay_token(session_id: UUID, admin: AdminUser, db: DbSession) -> ReplayTokenOut:
    """The waterfall regenerates persona audio exactly as report replay does (CLAUDE.md §1.8 —
    never stored). An admin is not the session owner, so the token is minted here under the
    admin gate instead of the owner-only `/sessions/{id}/replay-token`."""
    session = await db.get(Session, session_id)
    if session is None:
        raise NotFoundError("Session not found.")
    token = mint_replay_token(str(session.id), str(admin.id))
    return ReplayTokenOut(token=token, expires_in=REPLAY_TOKEN_TTL_SECONDS)


@router.get("/observability/sessions/{session_id}/recording")
async def admin_recording(session_id: UUID, admin: AdminUser, db: DbSession) -> Any:
    del admin
    from ..services import session_service

    session = await db.get(Session, session_id)
    if session is None:
        raise NotFoundError("Session not found.")
    return session_service.get_recording(session)


@router.get("/observability/model-calls")
async def model_calls(
    admin: AdminUser,
    db: DbSession,
    role: str | None = None,
    model: str | None = None,
    cached: bool | None = None,
    prompt_version: str | None = None,
    sort: str = "created_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    del admin
    return await observability_service.list_model_calls(
        db,
        role=role,
        model=model,
        cached=cached,
        prompt_version=prompt_version,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )


@router.get("/observability/cost")
async def cost(admin: AdminUser, db: DbSession) -> dict[str, Any]:
    del admin
    return await observability_service.cost_panel(db)


@router.get("/evals/versions")
async def versions(admin: AdminUser, db: DbSession) -> list[dict[str, Any]]:
    del admin
    return await evals_service.list_versions(db)


@router.get("/evals/runs")
async def runs(
    admin: AdminUser,
    db: DbSession,
    suite: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    del admin
    return await evals_service.list_runs(db, suite=suite, limit=limit)


@router.get("/evals/regression")
async def regression(admin: AdminUser, db: DbSession) -> dict[str, Any]:
    del admin
    return await evals_service.regression_series(db)


@router.get("/evals/cases")
async def cases(
    admin: AdminUser,
    db: DbSession,
    model_version: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    del admin
    return await evals_service.per_case_grid(db, model_version=model_version, limit=limit)


@router.get("/evals/score-versions")
async def score_versions(admin: AdminUser, db: DbSession) -> list[str]:
    del admin
    return await evals_service.score_versions(db)


@router.get("/evals/compare")
async def compare(
    admin: AdminUser,
    db: DbSession,
    version_a: str,
    version_b: str,
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    del admin
    return await evals_service.compare_versions(
        db, version_a=version_a, version_b=version_b, limit=limit
    )


@router.get("/evals/speech")
async def speech(admin: AdminUser, db: DbSession) -> list[dict[str, Any]]:
    del admin
    return await evals_service.speech_panel(db)
