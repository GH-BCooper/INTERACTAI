"""Task 1.1 acceptance: "Token reuse, wrong owner, expired token and closed session are each
rejected with the correct code — one test per case." Exercised against fake Redis/DB so this
runs with no real infrastructure; the real DB/Redis wiring is covered separately in
tests/integration/test_realtime_handshake.py.
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest

from services.realtime.app import handshake as hs
from services.realtime.app.core.config import get_settings
from services.realtime.app.session import SessionRegistry, SessionRuntime

SETTINGS = get_settings()


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def seed_jti(self, jti: str) -> None:
        self._store[f"ws_token_jti:{jti}"] = "1"

    async def getdel(self, key: str) -> str | None:
        return self._store.pop(key, None)


class _FakeSocket:
    async def send_text(self, data: str) -> None:  # pragma: no cover
        pass

    async def send_bytes(self, data: bytes) -> None:  # pragma: no cover
        pass


def _mint_token(
    *, session_id: str, user_id: str, jti: str | None = None, exp_delta: int = 120
) -> str:
    now = int(time.time())
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "jti": jti or str(uuid.uuid4()),
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(payload, SETTINGS.ws_token_secret, algorithm="HS256")


def _session_row(*, user_id: str, status: str = "active") -> dict[str, object]:
    return {"id": uuid.uuid4(), "user_id": uuid.UUID(user_id), "status": status}


@pytest.mark.asyncio
async def test_missing_token_rejected() -> None:
    decision = await hs.decide_handshake(
        token=None, redis=FakeRedis(), db=object(), registry=SessionRegistry(), settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "AUTH_INVALID_TOKEN"


@pytest.mark.asyncio
async def test_expired_token_rejected() -> None:
    user_id = str(uuid.uuid4())
    token = _mint_token(session_id=str(uuid.uuid4()), user_id=user_id, exp_delta=-10)
    decision = await hs.decide_handshake(
        token=token, redis=FakeRedis(), db=object(), registry=SessionRegistry(), settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "AUTH_INVALID_TOKEN"


@pytest.mark.asyncio
async def test_token_reuse_rejected() -> None:
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    token = _mint_token(session_id=str(uuid.uuid4()), user_id=user_id, jti=jti)
    redis = FakeRedis()  # jti never seeded -> getdel returns None -> "already burned"
    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=SessionRegistry(), settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "ORCHESTRATION_TOKEN_REUSED"


@pytest.mark.asyncio
async def test_wrong_owner_rejected_as_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = str(uuid.uuid4())
    token_user = str(uuid.uuid4())
    owner_user = str(uuid.uuid4())  # different from token_user
    jti = str(uuid.uuid4())
    token = _mint_token(session_id=session_id, user_id=token_user, jti=jti)
    redis = FakeRedis()
    redis.seed_jti(jti)

    async def fake_get_session_row(db: object, sid: uuid.UUID) -> dict[str, object]:
        return _session_row(user_id=owner_user)

    monkeypatch.setattr(hs, "get_session_row", fake_get_session_row)

    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=SessionRegistry(), settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "NOT_FOUND"


@pytest.mark.asyncio
async def test_closed_session_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    token = _mint_token(session_id=session_id, user_id=user_id, jti=jti)
    redis = FakeRedis()
    redis.seed_jti(jti)

    async def fake_get_session_row(db: object, sid: uuid.UUID) -> dict[str, object]:
        return _session_row(user_id=user_id, status="closed")

    monkeypatch.setattr(hs, "get_session_row", fake_get_session_row)

    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=SessionRegistry(), settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "NOT_FOUND"


@pytest.mark.asyncio
async def test_nonexistent_session_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    token = _mint_token(session_id=str(uuid.uuid4()), user_id=user_id, jti=jti)
    redis = FakeRedis()
    redis.seed_jti(jti)

    async def fake_get_session_row(db: object, sid: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(hs, "get_session_row", fake_get_session_row)

    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=SessionRegistry(), settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "NOT_FOUND"


@pytest.mark.asyncio
async def test_fresh_session_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    token = _mint_token(session_id=session_id, user_id=user_id, jti=jti)
    redis = FakeRedis()
    redis.seed_jti(jti)

    async def fake_get_session_row(db: object, sid: uuid.UUID) -> dict[str, object]:
        return _session_row(user_id=user_id, status="created")

    monkeypatch.setattr(hs, "get_session_row", fake_get_session_row)

    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=SessionRegistry(), settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.FRESH
    assert decision.claims is not None
    assert decision.claims.session_id == session_id


@pytest.mark.asyncio
async def test_second_socket_for_live_session_rejected_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    token = _mint_token(session_id=str(session_id), user_id=user_id, jti=jti)
    redis = FakeRedis()
    redis.seed_jti(jti)

    async def fake_get_session_row(db: object, sid: uuid.UUID) -> dict[str, object]:
        return _session_row(user_id=user_id, status="active")

    monkeypatch.setattr(hs, "get_session_row", fake_get_session_row)

    registry = SessionRegistry()
    live_runtime = SessionRuntime(
        session_id=session_id, user_id=uuid.UUID(user_id), websocket=_FakeSocket()
    )
    registry.try_register(live_runtime)  # disconnected_at is None -> "truly live"

    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=registry, settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "ORCHESTRATION_SESSION_BUSY"


@pytest.mark.asyncio
async def test_resume_offered_for_disconnected_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    token = _mint_token(session_id=str(session_id), user_id=user_id, jti=jti)
    redis = FakeRedis()
    redis.seed_jti(jti)

    async def fake_get_session_row(db: object, sid: uuid.UUID) -> dict[str, object]:
        return _session_row(user_id=user_id, status="active")

    monkeypatch.setattr(hs, "get_session_row", fake_get_session_row)

    registry = SessionRegistry()
    runtime = SessionRuntime(
        session_id=session_id, user_id=uuid.UUID(user_id), websocket=_FakeSocket()
    )
    registry.try_register(runtime)
    runtime.mark_disconnected()

    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=registry, settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.RESUMABLE
    assert decision.existing_runtime is runtime


@pytest.mark.asyncio
async def test_concurrent_session_cap_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = str(uuid.uuid4())

    async def fake_get_session_row(db: object, sid: uuid.UUID) -> dict[str, object]:
        return _session_row(user_id=user_id, status="created")

    monkeypatch.setattr(hs, "get_session_row", fake_get_session_row)

    registry = SessionRegistry()
    for _ in range(SETTINGS.max_concurrent_sessions):
        rt = SessionRuntime(
            session_id=uuid.uuid4(), user_id=uuid.UUID(user_id), websocket=_FakeSocket()
        )
        registry.try_register(rt)

    jti = str(uuid.uuid4())
    token = _mint_token(session_id=str(uuid.uuid4()), user_id=user_id, jti=jti)
    redis = FakeRedis()
    redis.seed_jti(jti)

    decision = await hs.decide_handshake(
        token=token, redis=redis, db=object(), registry=registry, settings=SETTINGS
    )
    assert decision.outcome is hs.HandshakeOutcome.REJECT
    assert decision.close_reason == "RATE_LIMITED"
