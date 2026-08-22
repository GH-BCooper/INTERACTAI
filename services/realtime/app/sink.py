"""The concrete `TurnSink` (Task 1.6): turns the pipeline's abstract `send_*`/`persist_*` calls
into real WS messages and real DB writes. Kept separate from `turn.py` on purpose — that module
stays free of WebSocket/DB imports, which is exactly what makes it testable without either.
"""

from __future__ import annotations

import asyncio
import time
import uuid as std_uuid
from typing import Any

import numpy as np
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .audio.protocol import FRAME_KIND_TTS_DOWN, encode_frame
from .coach_enqueue import ArqPoolLike
from .coach_enqueue import enqueue_score_turn as _enqueue_score_turn_job
from .core.ids import uuid7
from .core.logging import get_logger
from .db.repository import insert_turn, insert_turn_metrics
from .schemas.ws import (
    AudioChunkMeta,
    Degraded,
    Interrupted,
    LatencyReport,
    LatencyStage,
    PartialTranscript,
    PersonaText,
    ServerMachineState,
    Stage,
    StateChange,
    TurnFinalized,
    WordTiming,
)
from .session import SessionRuntime
from .state_machine import DegradedInfo

logger = get_logger(__name__)


class WsTurnSink:
    def __init__(
        self,
        websocket: WebSocket,
        runtime: SessionRuntime,
        sessionmaker: async_sessionmaker[AsyncSession],
        arq_pool: ArqPoolLike | None = None,
    ) -> None:
        self._ws = websocket
        self._runtime = runtime
        self._sessionmaker = sessionmaker
        self._arq_pool = arq_pool
        self._downstream_seq = 0
        # `process_turn` runs concurrently with the ingest loop (Task 1.5d needs mic frames
        # still being read while the persona is thinking/speaking), so two tasks can call
        # send_* at once. Starlette's WebSocket has no internal send lock; without this, two
        # concurrent sends can interleave and corrupt a frame.
        self._send_lock = asyncio.Lock()

    async def _send_control(self, msg: Any) -> None:
        """Every JSON control message goes through here — it's the one place that both sends
        and logs to `sent_message_log` (Task 2.2a's resume replay ring buffer), so no message
        type can accidentally be sent without becoming replayable."""
        data = msg.model_dump_json()
        async with self._send_lock:
            await self._ws.send_text(data)
        self._runtime.sent_message_log.append((msg.seq, data))

    async def _send_bytes(self, data: bytes) -> None:
        async with self._send_lock:
            await self._ws.send_bytes(data)

    async def send_state_change(
        self,
        state: str,
        *,
        turn_id: std_uuid.UUID | None = None,
        component: str | None = None,
        recoverable: bool = True,
    ) -> None:
        """The client-visible mapping is computed here from the machine, never passed in by the
        caller (Task 2.1) — that removes an entire class of caller/mapping drift that Phase 1's
        two-string-arguments version was exposed to. `component`/`recoverable` are only
        meaningful when `state == "degraded"`; see `state_machine.DegradedInfo`."""
        server_state = ServerMachineState(state)
        frm = self._runtime.state_machine.state
        degraded_info = (
            DegradedInfo(component=component, recoverable=recoverable)
            if server_state is ServerMachineState.degraded and component
            else None
        )
        self._runtime.state_machine.transition(server_state, degraded_info=degraded_info)
        duration_in_state_ms = self._runtime.state_machine.history[-1].duration_in_state_ms
        client_state = self._runtime.state_machine.client_state()
        logger.info(
            "state_transition",
            session_id=str(self._runtime.session_id),
            turn_id=str(turn_id) if turn_id else None,
            frm=frm.value,
            to=server_state.value,
            duration_in_state_ms=duration_in_state_ms,
            at_ms=self._runtime.elapsed_ms(),
        )
        msg = StateChange(
            type="state_change",
            seq=self._runtime.next_server_seq(),
            state=server_state,
            client_state=client_state,
            at_ms=self._runtime.elapsed_ms(),
        )
        await self._send_control(msg)

    async def send_partial_transcript(self, text: str, stability: float) -> None:
        msg = PartialTranscript(
            type="partial_transcript",
            seq=self._runtime.next_server_seq(),
            turn_index=self._runtime.turn_index,
            text=text,
            stability=stability,
            at_ms=self._runtime.elapsed_ms(),
        )
        await self._send_control(msg)

    async def send_turn_finalized(
        self,
        turn_id: std_uuid.UUID,
        text: str,
        start_ms: int,
        end_ms: int,
        confidence: float,
        words: list[dict[str, Any]],
    ) -> None:
        msg = TurnFinalized(
            type="turn_finalized",
            seq=self._runtime.next_server_seq(),
            turn_id=turn_id,
            turn_index=self._runtime.turn_index,
            text=text,
            start_ms=start_ms,
            end_ms=end_ms,
            asr_confidence=confidence,
            word_timings=[WordTiming(**w) for w in words],
        )
        await self._send_control(msg)

    async def send_persona_text(self, turn_id: std_uuid.UUID, delta: str, done: bool) -> None:
        msg = PersonaText(
            type="persona_text",
            seq=self._runtime.next_server_seq(),
            turn_id=turn_id,
            text_delta=delta,
            done=done,
        )
        await self._send_control(msg)

    async def send_audio_chunk(
        self,
        turn_id: std_uuid.UUID,
        chunk_seq: int,
        audio_int16: np.ndarray,
        sample_rate: int,
        is_final: bool,
    ) -> None:
        payload = audio_int16.astype("<i2").tobytes()
        meta = AudioChunkMeta(
            type="audio_chunk_meta",
            seq=self._runtime.next_server_seq(),
            turn_id=turn_id,
            chunk_seq=chunk_seq,
            sample_rate=sample_rate,
            byte_length=len(payload),
            is_final=is_final,
        )
        await self._send_control(meta)
        frame = encode_frame(
            kind=FRAME_KIND_TTS_DOWN,
            seq=self._downstream_seq,
            timestamp_ms=self._runtime.elapsed_ms(),
            payload=payload,
        )
        self._downstream_seq += 1
        await self._send_bytes(frame)
        # Feeds the `speaking` timeout approximation (docs/decisions/0008): "no forward
        # progress" is measured from the last chunk actually sent, not a guessed total duration.
        self._runtime.last_chunk_sent_monotonic = time.monotonic()

    async def send_degraded(self, component: str, message: str, recoverable: bool) -> None:
        msg = Degraded(
            type="degraded",
            seq=self._runtime.next_server_seq(),
            component=component,
            message=message,
            recoverable=recoverable,
        )
        await self._send_control(msg)

    async def send_latency_report(
        self, turn_id: std_uuid.UUID, stage_ms: dict[str, float], e2e_ms: float
    ) -> None:
        msg = LatencyReport(
            type="latency_report",
            seq=self._runtime.next_server_seq(),
            turn_id=turn_id,
            stages=[
                LatencyStage(stage=Stage(name), duration_ms=duration)
                for name, duration in stage_ms.items()
            ],
            e2e_ms=e2e_ms,
        )
        await self._send_control(msg)

    async def send_interrupted(
        self, turn_id: std_uuid.UUID, at_ms: int, truncated_text: str
    ) -> None:
        msg = Interrupted(
            type="interrupted",
            seq=self._runtime.next_server_seq(),
            turn_id=turn_id,
            at_ms=at_ms,
            truncated_text=truncated_text,
        )
        await self._send_control(msg)

    async def persist_turn(
        self,
        *,
        turn_id: std_uuid.UUID,
        index: int,
        speaker: str,
        text: str,
        start_ms: int,
        end_ms: int,
        word_timings: list[dict[str, Any]],
        truncated: bool,
        asr_confidence: float | None,
    ) -> None:
        async with self._sessionmaker() as db:
            await insert_turn(
                db,
                turn_id=turn_id,
                session_id=self._runtime.session_id,
                index=index,
                speaker=speaker,
                text=text,
                start_ms=start_ms,
                end_ms=end_ms,
                word_timings=word_timings,
                truncated=truncated,
                asr_confidence=asr_confidence,
            )

    async def persist_turn_metrics(
        self,
        *,
        turn_id: std_uuid.UUID,
        wpm: float,
        filler_count: int,
        filler_rate: float,
        longest_pause_ms: int,
        speech_ratio: float,
        word_count: int,
    ) -> None:
        async with self._sessionmaker() as db:
            await insert_turn_metrics(
                db,
                metrics_id=uuid7(),
                session_id=self._runtime.session_id,
                turn_id=turn_id,
                wpm=wpm,
                filler_count=filler_count,
                filler_rate=filler_rate,
                longest_pause_ms=longest_pause_ms,
                speech_ratio=speech_ratio,
                word_count=word_count,
            )

    async def enqueue_score_turn(self, turn_id: std_uuid.UUID) -> None:
        """Task 2.2d: "Fire and forget — never awaited." The caller (turn.py) awaits this
        method call itself (it has to — it's an `async def`), but this method's own body never
        awaits the actual enqueue; it fires a background task and returns immediately, so a slow
        or unreachable Redis can never add latency to the turn path. On failure the task buffers
        `turn_id` on the runtime for a retry at session close (`main.py::finalize_runtime`)."""

        async def _do_enqueue() -> None:
            ok = await _enqueue_score_turn_job(
                self._arq_pool, session_id=self._runtime.session_id, turn_id=turn_id
            )
            if not ok:
                self._runtime.pending_score_turn_ids.append(turn_id)

        asyncio.create_task(_do_enqueue())
