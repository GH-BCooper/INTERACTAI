from __future__ import annotations

import uuid

import pytest

from services.realtime.app.session import SessionRegistry, SessionRuntime


class _FakeSocket:
    async def send_text(self, data: str) -> None:  # pragma: no cover - unused in these tests
        pass

    async def send_bytes(self, data: bytes) -> None:  # pragma: no cover - unused in these tests
        pass


def _runtime(session_id: uuid.UUID | None = None) -> SessionRuntime:
    return SessionRuntime(
        session_id=session_id or uuid.uuid4(), user_id=uuid.uuid4(), websocket=_FakeSocket()
    )


def test_register_and_get() -> None:
    registry = SessionRegistry()
    rt = _runtime()
    assert registry.try_register(rt) is True
    assert registry.get(rt.session_id) is rt
    assert len(registry) == 1


def test_second_socket_for_live_session_rejected() -> None:
    registry = SessionRegistry()
    sid = uuid.uuid4()
    first = _runtime(sid)
    second = _runtime(sid)
    assert registry.try_register(first) is True
    assert registry.try_register(second) is False
    assert registry.get(sid) is first  # existing socket stays authoritative


def test_register_allowed_after_finalization() -> None:
    registry = SessionRegistry()
    sid = uuid.uuid4()
    first = _runtime(sid)
    registry.try_register(first)
    first.finalized = True  # simulate a completed finalize() without popping, edge safety
    second = _runtime(sid)
    assert registry.try_register(second) is True


@pytest.mark.asyncio
async def test_finalize_is_idempotent() -> None:
    registry = SessionRegistry()
    rt = _runtime()
    registry.try_register(rt)

    calls = 0

    async def finalizer(_runtime: SessionRuntime) -> None:
        nonlocal calls
        calls += 1

    await registry.finalize(rt.session_id, finalizer)
    await registry.finalize(rt.session_id, finalizer)  # second call must be a no-op

    assert calls == 1
    assert len(registry) == 0


@pytest.mark.asyncio
async def test_finalize_unknown_session_is_a_noop() -> None:
    registry = SessionRegistry()

    async def finalizer(_runtime: SessionRuntime) -> None:
        raise AssertionError("must never be called for an unknown session")

    await registry.finalize(uuid.uuid4(), finalizer)


def test_resume_grace_window_boundary() -> None:
    clock = {"t": 0.0}
    registry = SessionRegistry(resume_grace_s=90.0, clock=lambda: clock["t"])
    rt = _runtime()
    registry.try_register(rt)
    rt.disconnected_at = 0.0

    clock["t"] = 89.9
    assert registry.is_within_resume_grace(rt.session_id) is True
    assert registry.sweep_expired() == []

    clock["t"] = 90.1
    assert registry.is_within_resume_grace(rt.session_id) is False
    assert registry.sweep_expired() == [rt.session_id]


@pytest.mark.asyncio
async def test_sweeper_idempotent_finalizes_expired_runtime_once() -> None:
    clock = {"t": 0.0}
    registry = SessionRegistry(resume_grace_s=10.0, sweep_interval_s=1.0, clock=lambda: clock["t"])
    rt = _runtime()
    registry.try_register(rt)
    rt.mark_disconnected()
    rt.disconnected_at = 0.0

    calls = 0

    async def finalizer(_runtime: SessionRuntime) -> None:
        nonlocal calls
        calls += 1

    clock["t"] = 11.0
    expired = registry.sweep_expired()
    assert expired == [rt.session_id]

    # simulate the sweeper firing twice before finalize() has a chance to pop the entry
    await registry.finalize(rt.session_id, finalizer)
    await registry.finalize(rt.session_id, finalizer)
    assert calls == 1


@pytest.mark.asyncio
async def test_memory_does_not_grow_across_connect_disconnect_cycles() -> None:
    """Task 1.1 acceptance criterion: 20 sequential connect/disconnect cycles must not leak
    registry entries. Models the graceful path (explicit end_session -> immediate finalize),
    which is the common case main.py takes and does not need the 90s grace window at all."""
    registry = SessionRegistry()

    async def finalizer(_runtime: SessionRuntime) -> None:
        pass

    for _ in range(20):
        rt = _runtime()
        assert registry.try_register(rt) is True
        assert len(registry) == 1
        await registry.finalize(rt.session_id, finalizer)
        assert len(registry) == 0
