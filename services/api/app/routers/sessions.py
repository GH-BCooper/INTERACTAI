from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from ..core.config import get_settings
from ..core.deps import CurrentUser, DbSession
from ..core.exceptions import ForbiddenError, NotFoundError
from ..core.redis_client import get_redis
from ..core.security import REPLAY_TOKEN_TTL_SECONDS, mint_replay_token, mint_ws_token
from ..models import Session as SessionModel
from ..schemas.common import Page
from ..schemas.session import (
    AnnotationCreate,
    AnnotationOut,
    RecordingOut,
    ReplayTokenOut,
    ReportOut,
    RetryCreate,
    SessionCreate,
    SessionOut,
    SessionScoreOut,
    TurnOut,
    WsTokenOut,
)
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
        recording_consent=body.recording_consent,
        training_consent=body.training_consent,
    )
    await db.commit()
    return session_service.session_to_out(session)


@router.get("", response_model=Page[SessionOut])
async def list_sessions(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SessionOut]:
    sessions, total = await session_service.list_sessions(db, user.id, limit=limit, offset=offset)
    return Page(
        items=[session_service.session_to_out(s) for s in sessions],
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
    return session_service.session_to_out(session)


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


@router.post("/{session_id}/replay-token", response_model=ReplayTokenOut)
async def mint_session_replay_token(
    session_id: UUID, user: CurrentUser, db: DbSession
) -> ReplayTokenOut:
    """Task 3.4d: scopes the browser's direct calls to realtime's `POST /synthesize` for
    on-demand persona-audio regeneration during report replay. Ownership is checked here, once —
    the token itself is what proves that to realtime afterwards, so realtime never needs to
    query api's `sessions` table."""
    session = await _get_owned_or_raise(db, user, session_id)
    token = mint_replay_token(str(session.id), str(user.id))
    return ReplayTokenOut(token=token, expires_in=REPLAY_TOKEN_TTL_SECONDS)


@router.get("/{session_id}/report", response_model=ReportOut)
async def get_session_report(session_id: UUID, user: CurrentUser, db: DbSession) -> ReportOut:
    session = await _get_owned_or_raise(db, user, session_id)
    report = await session_service.get_report(db, session_id)
    if report is None:
        raise NotFoundError("The report has not been generated yet.")
    if report.status == "ready":
        # Task 4.1: the dashboard's attention panel's "an unread report" — set the instant a
        # ready report is actually returned to its owner, never re-cleared.
        await session_service.mark_report_viewed(db, session)
        await db.commit()
    return session_service.report_to_out(report)


@router.get("/{session_id}/turns", response_model=list[TurnOut])
async def get_session_turns(session_id: UUID, user: CurrentUser, db: DbSession) -> list[TurnOut]:
    await _get_owned_or_raise(db, user, session_id)
    return await session_service.list_turns_with_scores(db, session_id)


@router.get("/{session_id}/scores", response_model=list[SessionScoreOut])
async def get_session_scores(
    session_id: UUID, user: CurrentUser, db: DbSession
) -> list[SessionScoreOut]:
    session = await _get_owned_or_raise(db, user, session_id)
    return await session_service.list_session_scores(db, session)


@router.get("/{session_id}/recording", response_model=RecordingOut)
async def get_session_recording(session_id: UUID, user: CurrentUser, db: DbSession) -> RecordingOut:
    session = await _get_owned_or_raise(db, user, session_id)
    return session_service.get_recording(session)


@router.post("/{session_id}/annotations", response_model=AnnotationOut, status_code=201)
async def create_session_annotation(
    session_id: UUID, body: AnnotationCreate, user: CurrentUser, db: DbSession
) -> AnnotationOut:
    session = await _get_owned_or_raise(db, user, session_id)
    annotation = await session_service.create_annotation(db, session, user, body)
    await db.commit()
    return AnnotationOut.model_validate(annotation)


@router.post("/{session_id}/retry", response_model=SessionOut, status_code=201)
async def retry_session_question(
    session_id: UUID, body: RetryCreate, user: CurrentUser, db: DbSession, redis: RedisDep
) -> SessionOut:
    """Task 3.4f — "retry one question": a short new session seeded with exactly one question
    from this one, linked back for comparison."""
    session = await _get_owned_or_raise(db, user, session_id)
    retry = await session_service.create_retry_session(db, redis, user, session, body.turn_id)
    await db.commit()
    return session_service.session_to_out(retry)
