from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from ..core.config import get_settings
from ..core.deps import CurrentUser, DbSession
from ..core.exceptions import ForbiddenError, NotFoundError
from ..core.redis_client import get_redis
from ..core.security import mint_ws_token
from ..models import Session as SessionModel
from ..schemas.common import Page
from ..schemas.session import ReportOut, SessionCreate, SessionOut, WsTokenOut
from ..services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])

RedisDep = Annotated[Redis, Depends(get_redis)]


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    body: SessionCreate, user: CurrentUser, db: DbSession, redis: RedisDep
) -> SessionOut:
    session = await session_service.create_session(
        db,
        redis,
        user,
        scenario_id=body.scenario_id,
        difficulty=body.difficulty,
        target_minutes=body.target_minutes,
        focus_areas=body.focus_areas,
        resume_text_override=body.resume_text_override,
    )
    await db.commit()
    return SessionOut.model_validate(session)


@router.get("", response_model=Page[SessionOut])
async def list_sessions(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SessionOut]:
    sessions, total = await session_service.list_sessions(db, user.id, limit=limit, offset=offset)
    return Page(
        items=[SessionOut.model_validate(s) for s in sessions],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _get_owned_or_raise(db: DbSession, user: CurrentUser, session_id: UUID) -> SessionModel:
    session = await session_service.get_session_by_id(db, session_id)
    if session is None:
        raise NotFoundError("Session not found.")
    if session.user_id != user.id:
        raise ForbiddenError("This session belongs to a different account.")
    return session


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: UUID, user: CurrentUser, db: DbSession) -> SessionOut:
    session = await _get_owned_or_raise(db, user, session_id)
    return SessionOut.model_validate(session)


@router.post("/{session_id}/ws-token", response_model=WsTokenOut)
async def mint_session_ws_token(
    session_id: UUID, user: CurrentUser, db: DbSession, redis: RedisDep
) -> WsTokenOut:
    session = await _get_owned_or_raise(db, user, session_id)
    if session.status not in ("created", "active"):
        raise NotFoundError("Session is not open for connection.")

    settings = get_settings()
    token = await mint_ws_token(redis, str(session.id), str(user.id))
    return WsTokenOut(
        token=token,
        expires_in=settings.ws_token_ttl_seconds,
        ws_url=f"{settings.realtime_ws_url}?token={token}",
    )


@router.get("/{session_id}/report", response_model=ReportOut)
async def get_session_report(session_id: UUID, user: CurrentUser, db: DbSession) -> ReportOut:
    await _get_owned_or_raise(db, user, session_id)
    report = await session_service.get_report(db, session_id)
    if report is None:
        raise NotFoundError("The report has not been generated yet.")
    return ReportOut.model_validate(report)
