"""Task 2.2d: coach enqueue. Fake pool (not real ARQ/Redis) since what's under test here is
*this module's* fire-and-forget/failure-handling logic, not ARQ's own delivery guarantees —
those are exercised for real in services/coach's own tests against a real Redis."""

from __future__ import annotations

import uuid

import pytest

from services.realtime.app.coach_enqueue import (
    GENERATE_REPORT_JOB,
    SCORE_TURN_JOB,
    enqueue_generate_report,
    enqueue_score_turn,
)


class _RecordingPool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def enqueue_job(self, function: str, **kwargs: object) -> None:
        self.calls.append((function, kwargs))


class _FailingPool:
    async def enqueue_job(self, function: str, **kwargs: object) -> None:
        raise ConnectionError("redis unreachable")


class TestEnqueueScoreTurn:
    @pytest.mark.asyncio
    async def test_submits_the_right_job_name_and_args(self) -> None:
        pool = _RecordingPool()
        session_id, turn_id = uuid.uuid4(), uuid.uuid4()
        ok = await enqueue_score_turn(pool, session_id=session_id, turn_id=turn_id)
        assert ok is True
        assert pool.calls == [
            (SCORE_TURN_JOB, {"session_id": str(session_id), "turn_id": str(turn_id)})
        ]

    @pytest.mark.asyncio
    async def test_none_pool_returns_false_without_raising(self) -> None:
        ok = await enqueue_score_turn(None, session_id=uuid.uuid4(), turn_id=uuid.uuid4())
        assert ok is False

    @pytest.mark.asyncio
    async def test_redis_unreachable_returns_false_without_raising(self) -> None:
        """Task 2.2d: "If Redis is unreachable: log, buffer turn ids in memory... Never block
        the turn path." This is the "never raise into the caller" half of that contract — the
        buffering half lives in sink.py, which is what actually reacts to a False return."""
        ok = await enqueue_score_turn(_FailingPool(), session_id=uuid.uuid4(), turn_id=uuid.uuid4())
        assert ok is False


class TestEnqueueGenerateReport:
    @pytest.mark.asyncio
    async def test_submits_the_right_job_name_and_args(self) -> None:
        pool = _RecordingPool()
        session_id = uuid.uuid4()
        ok = await enqueue_generate_report(pool, session_id=session_id)
        assert ok is True
        assert pool.calls == [(GENERATE_REPORT_JOB, {"session_id": str(session_id)})]

    @pytest.mark.asyncio
    async def test_none_pool_returns_false_without_raising(self) -> None:
        ok = await enqueue_generate_report(None, session_id=uuid.uuid4())
        assert ok is False

    @pytest.mark.asyncio
    async def test_redis_unreachable_returns_false_without_raising(self) -> None:
        ok = await enqueue_generate_report(_FailingPool(), session_id=uuid.uuid4())
        assert ok is False
