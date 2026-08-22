"""Latency instrumentation (Task 1.6a) — written first, not last, per the spec's own
instruction: every optimisation made later is measured against this, not guessed.

No sampling: every stage, every turn, writes a `latency_events` row. Writes are batched and
fire-and-forget — buffered in memory, flushed every 2s or 50 rows (whichever comes first), and
flushed once more on session close. A latency write must never itself add latency to the turn
it is measuring, which is exactly why `record()` never awaits a DB call directly.
"""

from __future__ import annotations

import asyncio
import time
import uuid as std_uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from ..core.logging import get_logger
from ..schemas.ws import Stage

logger = get_logger(__name__)

FLUSH_INTERVAL_S = 2.0
FLUSH_BATCH_SIZE = 50

LatencyWriter = Callable[[list[dict[str, Any]]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PendingLatencyEvent:
    session_id: std_uuid.UUID
    turn_id: std_uuid.UUID
    stage: str
    duration_ms: float


class LatencyRecorder:
    """One instance per session. `writer` is injected (rather than a DB session directly) so
    this class has no DB dependency of its own — see db/repository.py's `insert_latency_events`
    for the production writer, and tests/unit/realtime/test_latency.py for a fake one."""

    def __init__(
        self,
        writer: LatencyWriter,
        *,
        flush_interval_s: float = FLUSH_INTERVAL_S,
        batch_size: int = FLUSH_BATCH_SIZE,
    ) -> None:
        self._writer = writer
        self._flush_interval_s = flush_interval_s
        self._batch_size = batch_size
        self._buffer: list[PendingLatencyEvent] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._pending_flushes: set[asyncio.Task[None]] = set()

    def record(
        self, session_id: std_uuid.UUID, turn_id: std_uuid.UUID, stage: Stage, duration_ms: float
    ) -> None:
        self._buffer.append(PendingLatencyEvent(session_id, turn_id, stage.value, duration_ms))
        if len(self._buffer) >= self._batch_size:
            task = asyncio.create_task(self.flush())
            self._pending_flushes.add(task)
            task.add_done_callback(self._pending_flushes.discard)

    async def flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch, self._buffer = self._buffer, []
        rows = [
            {
                "session_id": e.session_id,
                "turn_id": e.turn_id,
                "stage": e.stage,
                "duration_ms": e.duration_ms,
            }
            for e in batch
        ]
        await self._writer(rows)

    async def start_periodic_flush(self) -> None:
        async def _loop() -> None:
            while True:
                await asyncio.sleep(self._flush_interval_s)
                await self.flush()

        self._flush_task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        """Cancels the periodic flush and does one final flush — Task 1.1's "on disconnect,
        finalise: flush buffers" applies here too."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        if self._pending_flushes:
            await asyncio.gather(*self._pending_flushes, return_exceptions=True)
        await self.flush()


@asynccontextmanager
async def stage(
    recorder: LatencyRecorder,
    session_id: std_uuid.UUID,
    turn_id: std_uuid.UUID,
    name: Stage,
    **metadata: Any,
) -> AsyncGenerator[None]:
    """The one line every pipeline stage wraps itself in. `metadata` (e.g. Task 1.4's
    `rtf` on `asr_finalize`) has nowhere to live in the `latency_events` table itself — that
    table is exactly `(session_id, turn_id, stage, duration_ms)`, per CLAUDE.md §5's "a table,
    not a log line" for the *timing*. Metadata is genuinely supplementary context, not the
    headline claim, so it goes to a structured log line instead of forcing a schema change —
    see docs/decisions/0005-latency-stage-metadata.md."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        recorder.record(session_id, turn_id, name, duration_ms)
        if metadata:
            logger.info(
                "latency_stage_metadata",
                session_id=str(session_id),
                turn_id=str(turn_id),
                stage=name.value,
                duration_ms=duration_ms,
                **metadata,
            )
