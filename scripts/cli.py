#!/usr/bin/env python3
"""The terminal voice harness — the day-8 gate (docs/phase-1-BUILD.md Task 1.6b).

Talks to a running realtime service (`make realtime`, ws://localhost:8080/ws) over the same
binary protocol the browser will use (docs/03-realtime-protocol.md). Session creation and
ws-token minting reuse the real API business logic *in-process* — `services.api.app.services.
session_service.create_session` and `core.security.mint_ws_token` — against the same
Postgres/Redis `make up` provides, so this tool needs `make realtime` running but not a
separate `make api` process.

Usage:
    uv run python scripts/cli.py --scenario technical-standard --difficulty standard
    uv run python scripts/cli.py --replay tests/fixtures/audio/clean_utterance_3s.wav --persona-stub
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import websockets

for _stream in (sys.stdout, sys.stderr):
    # Windows' default console codepage (cp1252) can't encode the box-drawing/check-mark
    # glyphs printed below; force UTF-8 on both streams so this never crashes mid-session.
    if _stream.encoding is not None and _stream.encoding.lower() != "utf-8":
        _stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The binary frame header is FROZEN (Task 1.2b/1.2d) — duplicated here rather than imported
# from services.realtime.app.audio.protocol. Both services/api and services/realtime expose a
# top-level `app` package; this script needs api's business logic (bare `services.api.app...`
# import, fine) for session bootstrap AND the realtime wire format, and putting both service
# dirs on sys.path at once would collide on the name `app` (docs/decisions/0003's reasoning
# applies here too). Four constants and one struct format are cheaper to duplicate than to
# solve that for a debug script.
PROTOCOL_VERSION = 1
FRAME_KIND_MIC_UP = 1
FRAME_KIND_TTS_DOWN = 2
UPSTREAM_SAMPLE_RATE = 16_000
UPSTREAM_FRAME_SAMPLES = 320
UPSTREAM_PAYLOAD_BYTES = UPSTREAM_FRAME_SAMPLES * 2
HEADER_FORMAT = ">BBHII"
HEADER_BYTES = struct.calcsize(HEADER_FORMAT)

STAGE_ORDER = [
    "endpoint_detect",
    "asr_finalize",
    "prompt_assemble",
    "model_ttft",
    "first_chunk_assemble",
    "tts_first_chunk",
    "transport",
    "e2e",
]
BUDGET_E2E_MS = 1400


def encode_mic_frame(seq: int, timestamp_ms: int, payload: bytes) -> bytes:
    header = struct.pack(HEADER_FORMAT, PROTOCOL_VERSION, FRAME_KIND_MIC_UP, 0, seq, timestamp_ms)
    return header + payload


def decode_frame(data: bytes) -> tuple[int, int, int, bytes]:
    version, kind, _reserved, seq, timestamp_ms = struct.unpack(HEADER_FORMAT, data[:HEADER_BYTES])
    return version, kind, timestamp_ms, data[HEADER_BYTES:]


async def bootstrap_session(
    scenario_slug: str, difficulty: str, target_minutes: int
) -> tuple[str, str]:
    """Returns (ws_token, session_id). Reuses the real API business logic in-process."""
    from sqlalchemy import select

    from services.api.app.core.db import get_sessionmaker
    from services.api.app.core.redis_client import get_redis_pool
    from services.api.app.core.security import mint_ws_token
    from services.api.app.models import Scenario, User
    from services.api.app.services import session_service

    sessionmaker = get_sessionmaker()
    redis = get_redis_pool()

    async with sessionmaker() as db:
        result = await db.execute(select(Scenario).where(Scenario.slug == scenario_slug))
        scenario = result.scalar_one_or_none()
        if scenario is None:
            raise SystemExit(
                f"no scenario '{scenario_slug}' in the database — run `make seed` first "
                f"(or pick one of the slugs under content/scenarios/)"
            )

        result = await db.execute(select(User).where(User.email == "cli-dev@interactai.local"))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(email="cli-dev@interactai.local")
            db.add(user)
            await db.flush()

        session = await session_service.create_session(
            db,
            redis,
            user,
            scenario_id=scenario.id,
            difficulty=difficulty,
            target_minutes=target_minutes,
            focus_areas=[],
            resume_text_override=None,
        )
        await db.commit()
        session_id = str(session.id)
        token = await mint_ws_token(redis, session_id, str(user.id))

    return token, session_id


def read_replay_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if (
            w.getframerate() != UPSTREAM_SAMPLE_RATE
            or w.getnchannels() != 1
            or w.getsampwidth() != 2
        ):
            raise SystemExit(
                f"{path} is not 16kHz/mono/16-bit PCM — the frozen capture contract "
                f"(got {w.getframerate()}Hz, {w.getnchannels()}ch, {w.getsampwidth() * 8}-bit)"
            )
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16)


class StageTable:
    """Accumulates per-turn stage timings from `latency_report` messages for printing and for
    the final session summary's percentiles (Task 1.6b)."""

    def __init__(self) -> None:
        self.turns: list[dict[str, float]] = []

    def record(self, stages: dict[str, float]) -> None:
        self.turns.append(stages)

    def print_last(self) -> None:
        if not self.turns:
            return
        stages = self.turns[-1]
        print(f"\n  ┌─ turn {len(self.turns)} " + "─" * 40)
        for name in STAGE_ORDER:
            if name in stages and name != "e2e":
                print(f"  │ {name:<22} {stages[name]:>6.0f} ms")
        e2e = stages.get("e2e")
        if e2e is not None:
            verdict = "✅" if e2e <= BUDGET_E2E_MS else "⚠️"
            print("  │ " + "─" * 38)
            print(f"  │ {'e2e':<22} {e2e:>6.0f} ms   {verdict} (budget {BUDGET_E2E_MS})")
        print("  └" + "─" * 40)

    def print_summary(self, rtf_values: list[float]) -> None:
        print(f"\nsession summary — {len(self.turns)} turn(s)")
        for name in STAGE_ORDER:
            values = [t[name] for t in self.turns if name in t]
            if not values:
                continue
            p50 = statistics.median(values)
            p95 = (
                values[min(len(values) - 1, round(0.95 * (len(values) - 1)))]
                if len(values) > 1
                else values[0]
            )
            print(f"  {name:<22} p50={p50:>6.0f}ms  p95={p95:>6.0f}ms  n={len(values)}")
        if rtf_values:
            print(f"  {'rtf':<22} mean={statistics.mean(rtf_values):.2f}")


async def run_session(args: argparse.Namespace) -> int:
    token, session_id = await bootstrap_session(args.scenario, args.difficulty, args.target_minutes)
    print(f"  ✓ session created  · {session_id}")

    t_connect = time.perf_counter()
    async with websockets.connect(f"{args.realtime_url}?token={token}") as ws:
        capabilities = ["persona_stub"] if args.persona_stub else []
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "seq": 0,
                    "protocol_version": "1.0",
                    "session_id": session_id,
                    "client_sample_rate": UPSTREAM_SAMPLE_RATE,
                    "client_frame_ms": 20,
                    "capabilities": capabilities,
                }
            )
        )
        ready_raw = await ws.recv()
        ready = json.loads(ready_raw)
        if ready.get("type") != "ready":
            print(f"  ✗ handshake failed: {ready}", file=sys.stderr)
            return 1
        warmup_ms = (time.perf_counter() - t_connect) * 1000
        print(f"  ✓ ws connected     · warm-up {warmup_ms:.0f}ms")

        stage_table = StageTable()
        downstream_audio = bytearray()
        turn_done = asyncio.Event()
        opener_done = asyncio.Event()
        recv_task = asyncio.create_task(
            _receive_loop(ws, stage_table, downstream_audio, turn_done, opener_done)
        )

        if not args.persona_stub:
            # Task 2.3f's scripted opening line runs `idle -> thinking -> speaking -> idle`
            # before the user has said anything. `_receive_messages` (server-side) gates VAD/
            # state processing on that finishing (docs/decisions/0008's warm_up_complete) — a
            # real browser client wouldn't start capturing mic audio until the UI shows it's the
            # user's turn either, so sending replay audio immediately (the old behaviour) raced
            # the opener and lost the first ~2s of the utterance to the gate, silently, with a
            # truncated transcript as the only symptom. Waiting here matches real client timing
            # and makes replay runs measure the pipeline honestly. persona_stub never plays an
            # opener, so there's nothing to wait for there.
            try:
                await asyncio.wait_for(opener_done.wait(), timeout=8.0)
            except TimeoutError:
                print("  ⚠ opening line did not finish within 8s — sending anyway", file=sys.stderr)

        if args.replay:
            pcm = read_replay_wav(Path(args.replay))
        else:
            pcm = record_from_microphone(args.record_seconds)

        seq = 0
        n_frames = len(pcm) // UPSTREAM_FRAME_SAMPLES
        for i in range(n_frames):
            frame_samples = pcm[i * UPSTREAM_FRAME_SAMPLES : (i + 1) * UPSTREAM_FRAME_SAMPLES]
            payload = frame_samples.astype("<i2").tobytes()
            await ws.send(encode_mic_frame(seq, seq * 20, payload))
            seq += 1
            if not args.fast:
                await asyncio.sleep(0.02)  # real-time pacing — the endpointing cascade's
                # duration guards are wall-clock-based (Task 1.3c), so replay must not
                # outrun real time for those to mean anything.

        # trailing silence so the cascade actually observes an end of speech
        silence_frame = b"\x00\x00" * UPSTREAM_FRAME_SAMPLES
        for _ in range(75):  # 1.5s
            await ws.send(encode_mic_frame(seq, seq * 20, silence_frame))
            seq += 1
            if not args.fast:
                await asyncio.sleep(0.02)

        try:
            await asyncio.wait_for(turn_done.wait(), timeout=20.0)
        except TimeoutError:
            print("  ⚠ turn did not complete within 20s — closing anyway", file=sys.stderr)

        await ws.send(json.dumps({"type": "end_session", "seq": seq, "reason": "user_hangup"}))
        await asyncio.sleep(0.5)
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

        stage_table.print_summary([])

        if downstream_audio:
            out_path = REPO_ROOT / "data" / "recordings" / f"cli_reply_{session_id}.wav"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(out_path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24_000)  # DOWNSTREAM_SAMPLE_RATE — frozen, Task 1.5b
                w.writeframes(bytes(downstream_audio))
            print(f"\n  ✓ persona reply saved · {out_path}")
    return 0


def record_from_microphone(
    seconds: float,
) -> np.ndarray:  # pragma: no cover - needs real audio hardware
    import sounddevice as sd

    print(f"  recording {seconds:.0f}s from the microphone — speak now...")
    audio = sd.rec(
        int(seconds * UPSTREAM_SAMPLE_RATE),
        samplerate=UPSTREAM_SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    return audio.reshape(-1)


async def _receive_loop(
    ws: Any,
    stage_table: StageTable,
    downstream_audio: bytearray,
    turn_done: asyncio.Event,
    opener_done: asyncio.Event,
) -> None:
    # Task 2.3f added a scripted opening line: `idle -> thinking -> speaking -> idle` now fires
    # once on its own, before the replayed utterance has even finished sending, with no
    # `turn_finalized` preceding it (there's no user turn to finalize yet). Waiting for the
    # *first* speaking->idle cycle — this loop's original behaviour — fires on the opening line
    # instead of the reply to the replayed audio, so the CLI hung up mid-turn and every replay
    # run reported "0 turn(s)". A real reply cycle is only the one that follows a
    # `turn_finalized` for the utterance just sent. `opener_done` is that first cycle,
    # specifically — `run_session` waits on it before sending any audio (see there for why).
    seen_speaking = False
    seen_turn_finalized = False
    async for message in ws:
        if isinstance(message, bytes):
            _version, kind, _ts, payload = decode_frame(message)
            if kind == FRAME_KIND_TTS_DOWN:
                downstream_audio.extend(payload)
            continue

        payload = json.loads(message)
        msg_type = payload.get("type")
        if msg_type == "state_change":
            print(f"  ● {payload['state']}")
            if payload["state"] == "speaking":
                seen_speaking = True
            elif payload["state"] == "idle" and seen_speaking:
                if not seen_turn_finalized:
                    opener_done.set()  # the scripted opener's own cycle, not a user reply
                else:
                    turn_done.set()  # the reply to the replayed utterance finished
        elif msg_type == "turn_finalized":
            print(f'  › you: "{payload["text"]}"')
            seen_turn_finalized = True
            seen_speaking = False
        elif msg_type == "persona_text" and payload.get("text_delta"):
            print(f'  ♪ [persona] "{payload["text_delta"]}"')
        elif msg_type == "latency_report":
            stages = {s["stage"]: s["duration_ms"] for s in payload["stages"]}
            stages["e2e"] = payload["e2e_ms"]
            stage_table.record(stages)
            stage_table.print_last()
        elif msg_type == "degraded":
            print(f"  ⚠ degraded: {payload['component']} — {payload['message']}")
        elif msg_type == "interrupted":
            print(f'  ✗ interrupted — spoke: "{payload["truncated_text"]}"')
        elif msg_type == "error":
            print(f"  ✗ error {payload['code']}: {payload['message']}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scenario", default="technical-standard")
    parser.add_argument("--difficulty", default="standard")
    parser.add_argument("--target-minutes", type=int, default=5)
    parser.add_argument(
        "--replay", default=None, help="WAV file to feed instead of a live microphone"
    )
    parser.add_argument(
        "--record-seconds",
        type=float,
        default=15.0,
        help="mic recording length when --replay is omitted",
    )
    parser.add_argument(
        "--persona-stub",
        action="store_true",
        help="canned reply, isolates pipeline latency from model latency",
    )
    parser.add_argument(
        "--fast", action="store_true", help="skip real-time pacing (for CI, not for tuning)"
    )
    parser.add_argument("--realtime-url", default="ws://localhost:8080/ws")
    args = parser.parse_args()

    return asyncio.run(run_session(args))


if __name__ == "__main__":
    raise SystemExit(main())
