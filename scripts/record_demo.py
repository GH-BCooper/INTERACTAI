#!/usr/bin/env python3
"""Records the `/demo` sample session through the REAL pipeline — Phase 6 TASK 6.5.

Nothing in the demo is hand-authored except the user's scripted answers: a running realtime
service (`make realtime`) does the VAD, endpointing, ASR, persona and TTS, and a running coach
worker (`make coach`) scores and narrates afterwards. This script is the "user": it streams each
answer WAV at real-time pace, waits for the persona to finish replying, and assembles what a
listener would have heard into one timeline WAV (user audio where it was sent, persona audio
scheduled the way the browser's playback scheduler would play it).

Both voices are synthesized (answers with Piper `en_GB-alan-medium`, see data/demo_raw/) — the
demo page says so. Every latency figure it shows is the realtime service's own measurement.

Usage (with `make up`, `make realtime`, `make coach` running):
    uv run python scripts/record_demo.py --scenario behavioural-standard
    uv run python scripts/export_demo.py --session-id <printed id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import websockets

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.cli import (  # noqa: E402
    FRAME_KIND_TTS_DOWN,
    UPSTREAM_FRAME_SAMPLES,
    UPSTREAM_SAMPLE_RATE,
    bootstrap_session,
    decode_frame,
    encode_mic_frame,
    read_replay_wav,
)

RAW_DIR = REPO_ROOT / "data" / "demo_raw"
DOWNSTREAM_RATE = 24_000
PAUSE_BEFORE_ANSWER_S = 0.8


class Timeline:
    """What a listener hears, at 16 kHz. Persona chunks are queued back-to-back from the moment
    each arrives — the same rule as apps/web/lib/audio/playback.ts's scheduler."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.samples = np.zeros(UPSTREAM_SAMPLE_RATE * 600, dtype=np.int32)
        self.persona_cursor_s = 0.0
        self.segments: list[dict[str, Any]] = []

    def now_s(self) -> float:
        return time.perf_counter() - self.t0

    def _mix(self, start_s: float, pcm16k: np.ndarray) -> None:
        i = int(start_s * UPSTREAM_SAMPLE_RATE)
        self.samples[i : i + len(pcm16k)] += pcm16k.astype(np.int32)

    def add_user(self, start_s: float, pcm: np.ndarray) -> None:
        self._mix(start_s, pcm)
        self.segments.append(
            {
                "speaker": "user",
                "start_ms": start_s * 1000,
                "end_ms": (start_s + len(pcm) / 16000) * 1000,
            }
        )

    def add_persona_chunk(self, payload: bytes) -> None:
        pcm24 = np.frombuffer(payload, dtype="<i2").astype(np.float32)
        n16 = int(len(pcm24) * UPSTREAM_SAMPLE_RATE / DOWNSTREAM_RATE)
        pcm16 = np.interp(np.linspace(0, len(pcm24) - 1, n16), np.arange(len(pcm24)), pcm24).astype(
            np.int16
        )
        start = max(self.now_s(), self.persona_cursor_s)
        new_segment = (
            start > self.persona_cursor_s + 0.25
            or not self.segments
            or self.segments[-1]["speaker"] != "persona"
        )
        self._mix(start, pcm16)
        self.persona_cursor_s = start + len(pcm16) / UPSTREAM_SAMPLE_RATE
        if new_segment:
            self.segments.append({"speaker": "persona", "start_ms": start * 1000, "end_ms": 0.0})
        self.segments[-1]["end_ms"] = self.persona_cursor_s * 1000

    def write(self, path: Path) -> float:
        end_s = max(s["end_ms"] for s in self.segments) / 1000 + 0.5
        out = np.clip(self.samples[: int(end_s * UPSTREAM_SAMPLE_RATE)], -32768, 32767).astype(
            "<i2"
        )
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(UPSTREAM_SAMPLE_RATE)
            w.writeframes(out.tobytes())
        return end_s * 1000


async def run(args: argparse.Namespace) -> int:
    answers = sorted(RAW_DIR.glob("answer_*.wav"))
    if not answers:
        print("no data/demo_raw/answer_*.wav — generate them first", file=sys.stderr)
        return 1
    token, session_id = await bootstrap_session(args.scenario, args.difficulty, args.target_minutes)
    print(f"session {session_id}")
    timeline = Timeline()
    messages: list[dict[str, Any]] = []
    persona_idle = asyncio.Event()
    speaking_seen = False

    async with websockets.connect(f"{args.realtime_url}?token={token}", max_size=None) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "seq": 0,
                    "protocol_version": "1.0",
                    "session_id": session_id,
                    "client_sample_rate": UPSTREAM_SAMPLE_RATE,
                    "client_frame_ms": 20,
                    "capabilities": [],
                }
            )
        )
        ready = json.loads(await ws.recv())
        if ready.get("type") != "ready":
            print(f"handshake failed: {ready}", file=sys.stderr)
            return 1
        timeline.t0 = time.perf_counter()

        async def receive() -> None:
            nonlocal speaking_seen
            async for message in ws:
                if isinstance(message, bytes):
                    _v, kind, _ts, payload = decode_frame(message)
                    if kind == FRAME_KIND_TTS_DOWN:
                        timeline.add_persona_chunk(payload)
                    continue
                payload = json.loads(message)
                payload["_t_ms"] = timeline.now_s() * 1000
                messages.append(payload)
                kind = payload.get("type")
                if kind == "state_change":
                    if payload["state"] == "speaking":
                        speaking_seen = True
                        persona_idle.clear()
                    elif payload["state"] == "degraded":
                        speaking_seen = True  # a degraded turn still ends in idle (holding line)
                    elif payload["state"] == "idle" and speaking_seen:
                        persona_idle.set()
                elif kind == "turn_finalized":
                    print(f'  you: "{payload["text"]}"')
                elif kind == "latency_report":
                    print(f"  e2e {payload['e2e_ms']:.0f} ms")
                elif kind == "persona_text" and payload.get("text_delta"):
                    print(f"  persona: {payload['text_delta']}")

        recv_task = asyncio.create_task(receive())
        seq = 1
        silence = b"\x00\x00" * UPSTREAM_FRAME_SAMPLES

        async def send_silence(seconds: float) -> None:
            nonlocal seq
            for _ in range(int(seconds / 0.02)):
                await ws.send(encode_mic_frame(seq, seq * 20, silence))
                seq += 1
                await asyncio.sleep(0.02)

        for path in answers:
            await asyncio.wait_for(persona_idle.wait(), timeout=60)
            # Wait until the scheduled persona audio has actually finished "playing".
            while timeline.now_s() < timeline.persona_cursor_s:
                await send_silence(0.1)
            await send_silence(PAUSE_BEFORE_ANSWER_S)
            persona_idle.clear()
            speaking_seen = False
            pcm = read_replay_wav(path)
            timeline.add_user(timeline.now_s(), pcm)
            n = len(pcm) // UPSTREAM_FRAME_SAMPLES
            for i in range(n):
                frame = pcm[i * UPSTREAM_FRAME_SAMPLES : (i + 1) * UPSTREAM_FRAME_SAMPLES]
                await ws.send(encode_mic_frame(seq, seq * 20, frame.astype("<i2").tobytes()))
                seq += 1
                await asyncio.sleep(0.02)
            await send_silence(1.5)

        await asyncio.wait_for(persona_idle.wait(), timeout=60)
        while timeline.now_s() < timeline.persona_cursor_s + 0.3:
            await send_silence(0.1)
        await ws.send(json.dumps({"type": "end_session", "seq": seq, "reason": "user_hangup"}))
        await asyncio.sleep(2)
        recv_task.cancel()

    duration_ms = timeline.write(RAW_DIR / f"{session_id}_timeline.wav")
    (RAW_DIR / f"{session_id}_capture.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "duration_ms": duration_ms,
                "segments": timeline.segments,
                "messages": messages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"timeline written ({duration_ms / 1000:.1f}s) · session {session_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scenario", default="behavioural-standard")
    parser.add_argument("--difficulty", default="standard")
    parser.add_argument("--target-minutes", type=int, default=5)
    parser.add_argument("--realtime-url", default="ws://localhost:8080/ws")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
