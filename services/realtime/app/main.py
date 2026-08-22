"""The latency-critical service (CLAUDE.md §2) — one WebSocket per session. The handshake
(Task 1.1), audio ingest (Task 1.2c) and the full VAD -> endpointing -> ASR -> persona -> TTS
turn pipeline (Tasks 1.3-1.6) all meet in `_receive_loop` below.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid as std_uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect, WebSocketState

from .audio.ingest import SessionWavWriter
from .audio.protocol import UPSTREAM_SAMPLE_RATE, FrameDecodeError, validate_upstream_frame
from .audio.upload import RecordingResult, checkpoint_upload, finalize_recording, pcm_to_wav_bytes
from .coach_enqueue import ArqPoolLike, enqueue_generate_report
from .coach_enqueue import enqueue_score_turn as _retry_score_turn
from .core.config import get_settings
from .core.exceptions import AuthInvalidTokenError
from .core.logging import configure_logging, get_logger
from .core.redis_client import get_redis_pool
from .core.security import validate_replay_token
from .db.repository import close_session, insert_latency_events, insert_model_call, insert_turn
from .db.session import get_sessionmaker
from .endpointing.cascade import is_utterance_too_short
from .endpointing.semantic import check_semantic_completeness
from .frame_pipeline import do_interrupt, handle_interrupt_window, handle_speech_window
from .handshake import HandshakeOutcome, decide_handshake
from .metrics.latency import LatencyRecorder
from .persona.opening import deliver_opening_line
from .persona.prompt import PersonaContext, build_persona_context_from_brief
from .persona.question_plan import generate_question_plan
from .schemas.ws import Pong, Ready, ServerMachineState, SessionClosed, StateChange, WsError
from .session import SessionRegistry, SessionRuntime
from .sink import WsTurnSink
from .timeouts import run_state_watchdog
from .tts.piper import synthesize_chunk
from .turn import PipelineResources, UtteranceBuffer, float32_to_int16, int16_bytes_to_float32

logger = get_logger(__name__)

SYNTHESIZE_TIMEOUT_S = 10.0  # generous — this is an on-demand replay call, not on the turn path

PROTOCOL_MAJOR = "1"
RECORDINGS_DIR = Path("data") / "recordings"


class ModelRegistry:
    """Process-global model handles (Task 1.1: "Model loading happens once at process
    startup"). `/health/ready` reports `False` until both are resident."""

    def __init__(self) -> None:
        self.vad_session: Any | None = None
        self.asr_model: Any | None = None
        self.resources: PipelineResources | None = None

    @property
    def ready(self) -> bool:
        return (
            self.vad_session is not None
            and self.asr_model is not None
            and self.resources is not None
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    settings = get_settings()

    models = ModelRegistry()
    try:
        from .vad.silero import load_vad_session

        models.vad_session = load_vad_session(settings.vad_model_path)
    except Exception:
        logger.warning("vad_not_loaded")
    try:
        from .asr.whisper import load_asr_model

        models.asr_model = load_asr_model(
            settings.asr_model, compute_type=settings.asr_compute_type, device=settings.asr_device
        )
    except Exception:
        logger.warning("asr_not_loaded")

    try:
        from .asr.confidence import load_clarification_pool
        from .tts.piper import BackchannelCache, HoldingLine, IdlePromptCache, VoicePool

        voice_dir = Path(settings.piper_voice_dir)
        voice_pool = VoicePool(voice_dir)
        secondary_voice_id = settings.secondary_piper_voice
        # Task 1.5b/2.1: preloaded for every voice a seeded persona actually uses, not just the
        # default — a session's persona voice is almost always a non-default one.
        backchannel_cache = BackchannelCache()
        await backchannel_cache.preload(voice_pool, list(settings.persona_voice_ids))
        holding_line = HoldingLine()
        await holding_line.preload(voice_pool, settings.default_piper_voice)
        idle_prompt_cache = IdlePromptCache()
        for voice_id in settings.persona_voice_ids:
            await idle_prompt_cache.preload(voice_pool, voice_id)

        async def _model_calls_writer(**kwargs: Any) -> None:
            async with get_sessionmaker()() as db:
                await insert_model_call(db, **kwargs)

        models.resources = PipelineResources(
            asr_model=models.asr_model,
            voice_pool=voice_pool,
            backchannel_cache=backchannel_cache,
            holding_line=holding_line,
            idle_prompt_cache=idle_prompt_cache,
            model_calls_writer=_model_calls_writer,
            persona_model=settings.model_persona,
            persona_model_local=settings.model_persona_local,
            default_voice_id=settings.default_piper_voice,
            secondary_voice_id=secondary_voice_id,
            clarification_pool=load_clarification_pool(),
            max_tokens_per_turn=settings.max_tokens_per_turn,
        )
    except Exception:
        logger.exception("pipeline_resources_not_loaded")

    app.state.models = models
    app.state.registry = SessionRegistry(
        resume_grace_s=settings.resume_grace_s, sweep_interval_s=settings.sweeper_interval_s
    )

    try:
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception:
        # Task 2.2d: "If Redis is unreachable: log, buffer turn ids in memory... Never block
        # the turn path." A pool that never connected is just the permanent case of that —
        # every enqueue call below already tolerates `arq_pool is None`.
        logger.warning("arq_pool_not_available")
        app.state.arq_pool = None

    async def _finalize(runtime: SessionRuntime) -> None:
        # "error" here means "not one of the five specific named reasons" — the sweeper's own
        # abandoned-runtime path, not a claim that something broke. docs/decisions/0006.
        await finalize_runtime(runtime, end_reason="error", arq_pool=app.state.arq_pool)

    await app.state.registry.start_sweeper(_finalize)
    try:
        yield
    finally:
        await app.state.registry.stop_sweeper()
        if app.state.arq_pool is not None:
            await app.state.arq_pool.aclose()


app = FastAPI(title="InteractAI realtime", version="0.1.0", lifespan=lifespan)

# Task 3.4d: the only cross-origin REST surface this service exposes — `POST /synthesize`,
# called directly from the browser during report replay. The WS endpoint doesn't need this
# (WebSocket handshakes aren't subject to CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> JSONResponse:
    models: ModelRegistry = app.state.models
    if models.ready:
        return JSONResponse({"status": "ok"}, status_code=200)
    return JSONResponse({"status": "not_ready"}, status_code=503)


class SynthesizeRequest(BaseModel):
    token: str
    session_id: str
    text: str
    voice_id: str


@app.post("/synthesize")
async def synthesize(body: SynthesizeRequest) -> Response:
    """Task 3.4d: "Persona audio is regenerated on demand during replay from the transcript +
    voice_id — it was never stored (CLAUDE.md §1.8)." Deliberately outside the WS session
    entirely — a report can be replayed long after the session itself closed and its runtime
    was torn down — but still gated by a token only the API service (which already verified the
    caller owns this session) can mint (`validate_replay_token`, core/security.py). Not on any
    latency budget: a generous flat timeout, no deadline/fallback-voice/holding-line chain
    (Task 1.5b's cascade exists for the live turn path; a slow or failed replay synthesis just
    surfaces as one unplayable line in the transcript, per Task 3.4's own edge-case table)."""
    try:
        validate_replay_token(body.token, expected_session_id=body.session_id)
    except AuthInvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc

    models: ModelRegistry = app.state.models
    if models.resources is None:
        raise HTTPException(status_code=503, detail="Synthesis is not available yet.")

    try:
        result = await asyncio.wait_for(
            synthesize_chunk(models.resources.voice_pool, body.voice_id, body.text),
            timeout=SYNTHESIZE_TIMEOUT_S,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Synthesis timed out.") from exc
    except Exception as exc:
        logger.warning("replay_synthesis_failed", voice_id=body.voice_id)
        raise HTTPException(status_code=502, detail="Synthesis failed.") from exc

    if result is None:
        raise HTTPException(status_code=422, detail="No audio was produced for this text.")

    audio, sample_rate = result
    wav_bytes = pcm_to_wav_bytes(
        float32_to_int16(audio).tobytes(), sample_rate=sample_rate, channels=1
    )
    return Response(content=wav_bytes, media_type="audio/wav")


async def _latency_writer(rows: list[dict[str, Any]]) -> None:
    async with get_sessionmaker()() as db:
        await insert_latency_events(db, rows)


async def _finalize_abandoned_utterance(runtime: SessionRuntime) -> None:
    """Task 2.2b: "On timeout, the partial utterance is finalised as a truncated turn if it
    exceeds the minimum utterance length; otherwise discarded." Runs only when the runtime is
    being torn down (90s resume grace expired, or a genuine finalize) with speech still
    mid-flight — the ordinary end-of-utterance path (frame_pipeline.py) already handles the
    "connection stayed up" case; this is specifically the "connection did not come back" one.
    Best-effort text: whatever the partial-transcript pass last produced (Task 1.4), not a fresh
    final ASR pass — this is a best-effort salvage path for an already-lost connection, not
    somewhere to add a new blocking model call."""
    utt = runtime.current_utterance
    if not isinstance(utt, UtteranceBuffer):
        return
    duration_ms = len(utt.concat()) / UPSTREAM_SAMPLE_RATE * 1000
    runtime.current_utterance = None
    if is_utterance_too_short(duration_ms):
        return
    from .core.ids import uuid7

    turn_id = uuid7()
    end_ms = utt.start_ms + int(duration_ms)
    async with get_sessionmaker()() as db:
        await insert_turn(
            db,
            turn_id=turn_id,
            session_id=runtime.session_id,
            index=runtime.turn_index,
            speaker="user",
            text=utt.partial_transcript,
            start_ms=utt.start_ms,
            end_ms=end_ms,
            word_timings=[],
            truncated=True,
            asr_confidence=None,
        )
    logger.info(
        "abandoned_utterance_finalized",
        session_id=str(runtime.session_id),
        turn_id=str(turn_id),
        duration_ms=duration_ms,
    )


async def finalize_runtime(
    runtime: SessionRuntime, *, end_reason: str, arq_pool: ArqPoolLike | None = None
) -> None:
    """Task 1.1/2.2: flush buffers, finalize any mid-flight utterance, upload the recording
    (Task 2.2c), mark closed, enqueue the report job (Task 2.2d)."""
    if runtime.speaking_task is not None and not runtime.speaking_task.done():
        runtime.speaking_task.cancel()
    await _finalize_abandoned_utterance(runtime)
    if isinstance(runtime.latency_recorder, LatencyRecorder):
        await runtime.latency_recorder.stop()
    recording = RecordingResult(key=None, format=None, peaks=None)
    if runtime.wav_writer is not None:
        runtime.wav_writer.close()
        recording = await finalize_recording(
            runtime.wav_writer.path, user_id=runtime.user_id, session_id=runtime.session_id
        )
    async with get_sessionmaker()() as db:
        await close_session(
            db,
            runtime.session_id,
            end_reason=end_reason,
            duration_ms=runtime.elapsed_ms(),
            recording_key=recording.key,
            recording_format=recording.format,
            peaks=recording.peaks,
        )

    # Task 2.2d: retry any score_turn enqueues that failed mid-session, then enqueue the report
    # job — fire-and-forget from the caller's perspective (finalize_runtime is itself already
    # off the latency path by the time it runs), but each call is still tried and logged, never
    # silently skipped.
    #
    # Task 2.6 (AS-07): a distress exit is the one end_reason that skips this entirely — CLAUDE.
    # md §10 / the safety suite's acceptance criteria require "no scored report" for a session
    # the persona ended for genuine distress. Scoring is a judgement about interview performance;
    # a session that stopped being a practice interview partway through isn't one.
    if end_reason != "distress_exit":
        for turn_id in runtime.pending_score_turn_ids:
            await _retry_score_turn(arq_pool, session_id=runtime.session_id, turn_id=turn_id)
        await enqueue_generate_report(arq_pool, session_id=runtime.session_id)
    runtime.pending_score_turn_ids.clear()

    logger.info(
        "session_finalized",
        session_id=str(runtime.session_id),
        end_reason=end_reason,
        turns=runtime.turn_index,
    )


async def _begin_closing(
    websocket: WebSocket,
    runtime: SessionRuntime,
    registry: SessionRegistry,
    sink: WsTurnSink,
    *,
    end_reason: str,
    arq_pool: ArqPoolLike | None = None,
) -> None:
    """The single graceful-shutdown path (Task 2.1's `closing` state): client `end_session`,
    the idle-abandon watchdog trigger, and any future caller all fund through here so `closing`
    is only ever entered once per session. Bounds finalize (upload, DB close, coach enqueue) to
    Task 2.1's 30s `closing` timeout with `asyncio.wait_for` — if it doesn't finish in time, the
    session is force-closed anyway and a lost-flush incident is logged; the finalize task itself
    is left to run to completion in the background rather than cancelled, since a cancelled
    upload is worse than a slow one. Idempotent: a runtime already `closing`/`closed` is a
    no-op, matching `SessionRegistry.finalize`'s own idempotency."""
    if runtime.state_machine.state in (ServerMachineState.closing, ServerMachineState.closed):
        return
    if runtime.state_machine.can_transition(ServerMachineState.closing):
        await sink.send_state_change("closing")
    runtime.closing_started_monotonic = time.monotonic()

    async def _finalize(rt: SessionRuntime) -> None:
        await finalize_runtime(rt, end_reason=end_reason, arq_pool=arq_pool)

    finalize_task = asyncio.ensure_future(registry.finalize(runtime.session_id, _finalize))
    try:
        await asyncio.wait_for(asyncio.shield(finalize_task), timeout=30.0)
    except TimeoutError:
        logger.error(
            "closing_lost_flush_incident", session_id=str(runtime.session_id), end_reason=end_reason
        )
    except Exception:
        logger.exception("finalize_failed", session_id=str(runtime.session_id))

    if runtime.state_machine.can_transition(ServerMachineState.closed):
        await sink.send_state_change("closed")

    closed_msg = SessionClosed(
        type="session_closed",
        seq=runtime.next_server_seq(),
        reason=end_reason,
        duration_ms=runtime.elapsed_ms(),
        report_pending=end_reason != "distress_exit",  # Task 2.6/AS-07: never for a distress exit
    )
    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.send_text(closed_msg.model_dump_json())
        await websocket.close(code=1000)


async def _send_error(
    websocket: WebSocket,
    runtime: SessionRuntime,
    *,
    code: str,
    message: str,
    recovery: str,
    fatal: bool,
) -> None:
    err = WsError(
        type="error",
        seq=runtime.next_server_seq(),
        code=code,
        message=message,
        recovery=recovery,
        fatal=fatal,
        trace_id=str(std_uuid.uuid4()),
    )
    await websocket.send_text(err.model_dump_json())


async def _complete_hello(
    websocket: WebSocket, runtime: SessionRuntime, settings: Any, brief: dict[str, Any]
) -> bool:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=settings.handshake_timeout_s)
    except TimeoutError:
        await _send_error(
            websocket,
            runtime,
            code="ORCHESTRATION_HANDSHAKE_TIMEOUT",
            message="No hello arrived in time.",
            recovery="Reconnect.",
            fatal=True,
        )
        await websocket.close(code=1008)
        return False

    payload = json.loads(raw)
    if payload.get("type") != "hello":
        await _send_error(
            websocket,
            runtime,
            code="ORCHESTRATION_PROTOCOL_MISMATCH",
            message="Expected hello as the first message.",
            recovery="Reconnect.",
            fatal=True,
        )
        await websocket.close(code=1008)
        return False

    client_major = str(payload.get("protocol_version", "")).split(".", 1)[0]
    if (
        client_major != PROTOCOL_MAJOR
        or payload.get("client_sample_rate") != settings.audio_sample_rate
        or payload.get("client_frame_ms") != settings.audio_frame_ms
    ):
        await _send_error(
            websocket,
            runtime,
            code="ORCHESTRATION_PROTOCOL_MISMATCH",
            message="Protocol version or audio contract mismatch.",
            recovery="Reload the app.",
            fatal=True,
        )
        await websocket.close(code=1008)
        return False

    capabilities = payload.get("capabilities") or []
    runtime.persona_stub = "persona_stub" in capabilities
    # Task 2.3: the session's actual persona voice, not the process default — a session whose
    # persona is e.g. `en_US-ryan-medium` must not silently speak as the default voice instead.
    runtime.voice_id = brief.get("persona_voice_id") or settings.default_piper_voice
    if not runtime.persona_stub:
        runtime.persona_context = build_persona_context_from_brief(brief)

    ready = Ready(
        type="ready",
        seq=runtime.next_server_seq(),
        session_id=runtime.session_id,
        server_sample_rate=settings.audio_sample_rate,
        protocol_version=f"{PROTOCOL_MAJOR}.0",
        resumed=False,
    )
    await websocket.send_text(ready.model_dump_json())
    runtime.state_machine.transition(ServerMachineState.idle)
    return True


async def _complete_resume(websocket: WebSocket, runtime: SessionRuntime, settings: Any) -> bool:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=settings.handshake_timeout_s)
    except TimeoutError:
        await websocket.close(code=1008)
        return False

    payload = json.loads(raw)
    if payload.get("type") != "resume":
        await _send_error(
            websocket,
            runtime,
            code="ORCHESTRATION_PROTOCOL_MISMATCH",
            message="Expected resume as the first message.",
            recovery="Reconnect.",
            fatal=True,
        )
        await websocket.close(code=1008)
        return False

    last_server_seq = payload.get("last_server_seq")
    runtime.mark_reconnected(websocket)
    ready = Ready(
        type="ready",
        seq=runtime.next_server_seq(),
        session_id=runtime.session_id,
        server_sample_rate=settings.audio_sample_rate,
        protocol_version=f"{PROTOCOL_MAJOR}.0",
        resumed=True,
    )
    await websocket.send_text(ready.model_dump_json())

    # Task 2.2a: "the client is told which state it is in" — sent as a real StateChange so the
    # resumed client's UI has the same source of truth as a fresh connection would, not a
    # special-cased resume-only message shape.
    client_state = runtime.state_machine.client_state()
    state_msg = StateChange(
        type="state_change",
        seq=runtime.next_server_seq(),
        state=runtime.state_machine.state,
        client_state=client_state,
        at_ms=runtime.elapsed_ms(),
    )
    await websocket.send_text(state_msg.model_dump_json())

    if isinstance(last_server_seq, int):
        replayed = _replay_missed_messages(websocket, runtime, last_server_seq)
    else:
        replayed = 0
    logger.info(
        "session_resumed",
        session_id=str(runtime.session_id),
        state=runtime.state_machine.state.value,
        replayed_messages=replayed,
    )
    return True


def _replay_missed_messages(
    websocket: WebSocket, runtime: SessionRuntime, last_server_seq: int
) -> int:
    """Task 2.2a: "Server replays any control messages the client missed from a bounded ring
    buffer (last 100 messages). Audio is not replayed." `sent_message_log` (session.py) is that
    buffer — populated by `WsTurnSink._send_control`, so every control message this process ever
    actually sent to this session is a candidate, oldest-missed-first, capped by whatever the
    100-message window still holds (an outage longer than that loses only the oldest messages in
    it, never crashes or fabricates one)."""
    to_replay = [(seq, data) for seq, data in runtime.sent_message_log if seq > last_server_seq]
    for _seq, data in to_replay:
        asyncio.ensure_future(websocket.send_text(data))
    return len(to_replay)


RECORDING_CHECKPOINT_INTERVAL_S = 60.0


async def _run_checkpoint_uploads(runtime: SessionRuntime, wav_writer: SessionWavWriter) -> None:
    """Task 2.2c: periodic checkpoint re-upload — see docs/decisions/0009 for why this is the
    mechanism instead of true S3 multipart. Runs alongside the receive loop, cancelled on
    disconnect/finalize (same lifecycle as the state watchdog and the latency flush loop)."""
    while True:
        await asyncio.sleep(RECORDING_CHECKPOINT_INTERVAL_S)
        await checkpoint_upload(
            wav_writer.path, user_id=runtime.user_id, session_id=runtime.session_id
        )
        runtime.last_checkpoint_monotonic = time.monotonic()


async def _warm_up_persona(
    runtime: SessionRuntime, resources: PipelineResources, sink: WsTurnSink
) -> None:
    """Task 2.3b/2.3f, run once, off the critical path, right as a fresh session starts.
    Generating the question plan and delivering the opening line are independent (different
    model roles, and the plan has no client-visible side effect) — run concurrently rather
    than making the opening line wait on the planner call."""
    persona_context = runtime.persona_context
    if not isinstance(persona_context, PersonaContext):
        return
    settings = get_settings()

    async def _plan() -> None:
        plan = await generate_question_plan(
            settings.model_planner,
            scenario_brief=persona_context.scenario_brief,
            opening_strategy=persona_context.opening_strategy,
            resume_text=persona_context.resume_text,
            focus_areas=persona_context.focus_areas,
            target_minutes=persona_context.target_minutes,
        )
        runtime.question_plan = plan

    plan_task = asyncio.create_task(_plan())
    try:
        await deliver_opening_line(runtime=runtime, resources=resources, sink=sink)
    except Exception:
        # Live-run finding (docs/decisions/0008): a replay client (or a fast-talking real user)
        # can race the ingest loop into `listening` before this reaches its own `idle ->
        # thinking` transition, making the opening line's transition illegal. Never let that
        # (or any other opening-line failure) leave `warm_up_complete` stuck False — that would
        # silently wedge the whole session's VAD/state processing forever.
        logger.warning("opening_line_delivery_failed", session_id=str(runtime.session_id))
    finally:
        runtime.warm_up_complete = True
    await plan_task


async def _receive_loop(
    websocket: WebSocket,
    runtime: SessionRuntime,
    registry: SessionRegistry,
    resources: PipelineResources,
) -> None:
    settings = get_settings()
    if runtime.wav_writer is None:
        runtime.wav_writer = SessionWavWriter(RECORDINGS_DIR / f"{runtime.session_id}.wav")
    wav_writer = runtime.wav_writer
    arq_pool: ArqPoolLike | None = getattr(websocket.app.state, "arq_pool", None)

    latency = LatencyRecorder(_latency_writer)
    runtime.latency_recorder = latency
    await latency.start_periodic_flush()
    sink = WsTurnSink(websocket, runtime, get_sessionmaker(), arq_pool)

    if (
        isinstance(runtime.persona_context, PersonaContext)
        and not runtime.persona_stub
        and not runtime.persona_history
        and runtime.question_plan is None
    ):
        # Task 2.3b/2.3f: off the critical path — fired once, right as the session actually
        # starts, never on a resume (the opening line already played before the disconnect;
        # `persona_history`/`question_plan` being non-empty is exactly how a resumed runtime is
        # told apart from a fresh one here, since both share the same code path).
        # `warm_up_complete=False` gates VAD/state processing in `_receive_messages` until this
        # finishes — see `SessionRuntime.warm_up_complete`'s docstring for the race it closes.
        runtime.warm_up_complete = False
        asyncio.create_task(_warm_up_persona(runtime, resources, sink))

    semantic_checker = None
    if settings.model_endpointer:
        semantic_checker = lambda tail: check_semantic_completeness(settings.model_endpointer, tail)  # noqa: E731

    async def _on_idle_abandon() -> None:
        await _begin_closing(
            websocket, runtime, registry, sink, end_reason="user_abandoned", arq_pool=arq_pool
        )

    async def _on_distress_exit() -> None:
        await _begin_closing(
            websocket, runtime, registry, sink, end_reason="distress_exit", arq_pool=arq_pool
        )

    watchdog_task = asyncio.create_task(
        run_state_watchdog(
            runtime,
            resources,
            sink,
            on_idle_abandon=_on_idle_abandon,
            on_distress_exit=_on_distress_exit,
        )
    )
    checkpoint_task = asyncio.create_task(_run_checkpoint_uploads(runtime, wav_writer))
    try:
        await _receive_messages(
            websocket,
            runtime,
            registry,
            resources,
            sink,
            latency,
            wav_writer,
            semantic_checker,
            arq_pool,
        )
    finally:
        for task in (watchdog_task, checkpoint_task):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _receive_messages(
    websocket: WebSocket,
    runtime: SessionRuntime,
    registry: SessionRegistry,
    resources: PipelineResources,
    sink: WsTurnSink,
    latency: LatencyRecorder,
    wav_writer: SessionWavWriter,
    semantic_checker: Any,
    arq_pool: ArqPoolLike | None,
) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))

        if (data := message.get("bytes")) is not None:
            try:
                frame = validate_upstream_frame(data)
            except FrameDecodeError as exc:
                await _send_error(
                    websocket,
                    runtime,
                    code="CAPTURE_FRAME_MALFORMED",
                    message=str(exc),
                    recovery="Frame dropped; capture continues.",
                    fatal=False,
                )
                continue

            if not runtime.rate_limiter.allow():
                continue

            gap = runtime.seq_tracker.observe(frame.seq)
            if gap.gap_frames:
                wav_writer.write_silence(len(frame.payload), gap.gap_frames)
            if gap.degraded:
                await sink.send_degraded("transport", f"{gap.gap_frames}-frame sequence gap", True)

            wav_writer.write_frame(frame.payload)

            if not runtime.muted and runtime.vad is not None and runtime.warm_up_complete:
                samples = int16_bytes_to_float32(frame.payload)
                for window in runtime.frame_accumulator.push(samples):
                    now_ms = float(runtime.elapsed_ms())
                    state = runtime.state_machine.state
                    if state is ServerMachineState.speaking:
                        if await handle_interrupt_window(runtime=runtime, window=window):
                            await do_interrupt(runtime=runtime, sink=sink)
                    elif state in (
                        ServerMachineState.idle,
                        ServerMachineState.listening,
                        ServerMachineState.endpointing,
                    ):
                        await handle_speech_window(
                            runtime=runtime,
                            resources=resources,
                            latency=latency,
                            sink=sink,
                            window=window,
                            now_ms=now_ms,
                            semantic_checker=semantic_checker,
                        )
            continue

        if (text := message.get("text")) is not None:
            payload = json.loads(text)
            msg_type = payload.get("type")
            if msg_type == "ping":
                pong = Pong(
                    type="pong",
                    seq=runtime.next_server_seq(),
                    client_time_ms=payload.get("client_time_ms", 0),
                    server_time_ms=int(time.time() * 1000),
                )
                await websocket.send_text(pong.model_dump_json())
            elif msg_type == "mute":
                runtime.muted = bool(payload.get("muted", False))
            elif msg_type == "end_session":
                reason = payload.get("reason", "user_hangup")
                await _begin_closing(
                    websocket, runtime, registry, sink, end_reason=reason, arq_pool=arq_pool
                )
                return


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str | None = None) -> None:
    registry: SessionRegistry = websocket.app.state.registry
    models: ModelRegistry = websocket.app.state.models
    settings = get_settings()
    redis = get_redis_pool()

    async with get_sessionmaker()() as db:
        decision = await decide_handshake(
            token=token, redis=redis, db=db, registry=registry, settings=settings
        )

    if decision.outcome is HandshakeOutcome.REJECT:
        await websocket.close(code=decision.close_code or 1008, reason=decision.close_reason or "")
        return

    await websocket.accept()
    if decision.claims is None:
        raise RuntimeError("non-REJECT handshake decision must carry claims")

    if decision.outcome is HandshakeOutcome.RESUMABLE:
        if decision.existing_runtime is None:
            raise RuntimeError("RESUMABLE handshake decision must carry existing_runtime")
        runtime = decision.existing_runtime
        structlog.contextvars.bind_contextvars(session_id=str(runtime.session_id))
        if not await _complete_resume(websocket, runtime, settings):
            return
    else:
        runtime = SessionRuntime(
            session_id=std_uuid.UUID(decision.claims.session_id),
            user_id=std_uuid.UUID(decision.claims.user_id),
            websocket=websocket,
        )
        if models.vad_session is not None:
            runtime.attach_vad(models.vad_session)
        structlog.contextvars.bind_contextvars(session_id=str(runtime.session_id))
        if not registry.try_register(runtime):
            await websocket.close(code=4409, reason="ORCHESTRATION_SESSION_BUSY")
            return
        brief: dict[str, Any] = (decision.session_row or {}).get("brief") or {}
        if not await _complete_hello(websocket, runtime, settings, brief):
            pool: ArqPoolLike | None = getattr(websocket.app.state, "arq_pool", None)
            await registry.finalize(
                runtime.session_id,
                lambda rt: finalize_runtime(rt, end_reason="error", arq_pool=pool),
            )
            return

    try:
        if models.resources is None:
            raise RuntimeError("pipeline resources failed to load at startup")
        await _receive_loop(websocket, runtime, registry, models.resources)
    except WebSocketDisconnect:
        runtime.mark_disconnected()
        logger.info("session_disconnected", session_id=str(runtime.session_id))
    finally:
        structlog.contextvars.clear_contextvars()
