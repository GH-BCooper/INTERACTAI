"""Task 2.2d: enqueueing into the coach's ARQ queue. `services/coach` is the consumer
(`services/coach/app/worker.py`'s `score_turn`/`generate_report` functions); this module is
only ever a producer — realtime never imports coach's code, only agrees with it on job names
and argument shapes (the same "shared contract, no shared code" pattern as
docs/decisions/0003-realtime-db-access.md).

Both enqueue calls are fire-and-forget from the caller's perspective: `enqueue_score_turn` is
called from `sink.py` without being awaited by the turn-processing path (CLAUDE.md §2: the coach
never runs on the latency path, and that includes the cost of *scheduling* it). If Redis is
unreachable, the turn_id is buffered on the runtime and retried once at session close
(`flush_pending_score_turns`) — never silently dropped.
"""

from __future__ import annotations

import uuid as std_uuid
from typing import Protocol

from .core.logging import get_logger

logger = get_logger(__name__)

SCORE_TURN_JOB = "score_turn"
GENERATE_REPORT_JOB = "generate_report"


class ArqPoolLike(Protocol):
    async def enqueue_job(self, function: str, **kwargs: object) -> object | None: ...


async def enqueue_score_turn(
    pool: ArqPoolLike | None, *, session_id: std_uuid.UUID, turn_id: std_uuid.UUID
) -> bool:
    """Returns True if the job was actually submitted. Never raises — a scoring job that never
    got enqueued is a recoverable problem (retried at session close), not a turn-path failure."""
    if pool is None:
        return False
    try:
        await pool.enqueue_job(SCORE_TURN_JOB, session_id=str(session_id), turn_id=str(turn_id))
        return True
    except Exception:
        logger.warning(
            "score_turn_enqueue_failed", session_id=str(session_id), turn_id=str(turn_id)
        )
        return False


async def enqueue_generate_report(pool: ArqPoolLike | None, *, session_id: std_uuid.UUID) -> bool:
    """Task 2.2d: "enqueue generate_report with a dependency on all outstanding score_turn jobs
    for that session." ARQ has no native job-DAG; the dependency is implemented on the consumer
    side instead — `generate_report` (services/coach/app/worker.py) checks whether every turn
    has a scored row yet and re-defers itself if not, rather than the producer trying to track
    job completion here."""
    if pool is None:
        return False
    try:
        await pool.enqueue_job(GENERATE_REPORT_JOB, session_id=str(session_id))
        return True
    except Exception:
        logger.warning("generate_report_enqueue_failed", session_id=str(session_id))
        return False
