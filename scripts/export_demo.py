#!/usr/bin/env python3
"""Exports a recorded session to the static `/demo` bundle — Phase 6 TASK 6.5.

Reads the session back through the API's own serializers (`session_service.*`, the exact
functions behind GET /sessions/{id}, /turns, /scores, /report) so the JSON has the same shape
the real report components consume. Turn timings are re-based onto the listener timeline that
`scripts/record_demo.py` assembled; text, scores, evidence spans and word timings are untouched.
Per-turn latency is the realtime service's own `latency_events` measurement.

Usage: uv run python scripts/export_demo.py --session-id <id>
Writes: apps/web/public/demo/sample-session.json, apps/web/public/demo/sample-session.mp3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"
for _p in (str(REPO_ROOT), str(API_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import select  # noqa: E402

from app.core.db import get_sessionmaker  # noqa: E402
from app.models import LatencyEvent, ModelCall, Persona, Scenario  # noqa: E402
from app.services import session_service  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "demo_raw"
OUT_DIR = REPO_ROOT / "apps" / "web" / "public" / "demo"
PEAK_BUCKETS = 800


def _peaks(wav_path: Path) -> list[float]:
    import numpy as np

    with wave.open(str(wav_path)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32)
    size = max(1, len(pcm) // PEAK_BUCKETS)
    return [
        round(float(np.abs(pcm[i : i + size]).max()) / 32768.0, 3)
        for i in range(0, size * PEAK_BUCKETS, size)
    ]


def _merge_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for seg in sorted(segments, key=lambda s: s["start_ms"]):
        if merged and merged[-1]["speaker"] == seg["speaker"] == "persona":
            merged[-1]["end_ms"] = max(merged[-1]["end_ms"], seg["end_ms"])
        else:
            merged.append(dict(seg))
    return merged


async def export(session_id: str) -> None:
    capture = json.loads((RAW_DIR / f"{session_id}_capture.json").read_text(encoding="utf-8"))
    segments = _merge_segments(capture["segments"])
    async with get_sessionmaker()() as db:
        session = await session_service.get_session_by_id(db, session_id)  # type: ignore[arg-type]
        if session is None:
            raise SystemExit(f"session {session_id} not found")
        scenario = await db.get(Scenario, session.scenario_id)
        persona = (
            await db.get(Persona, scenario.persona_id) if scenario and scenario.persona_id else None
        )
        turns = await session_service.list_turns_with_scores(db, session.id)
        scores = await session_service.list_session_scores(db, session)
        report = await session_service.get_report(db, session.id)
        if report is None or report.status != "ready":
            raise SystemExit("report not ready yet — is the coach worker running?")
        latency_rows = (
            await db.execute(
                select(
                    LatencyEvent.turn_id,
                    LatencyEvent.stage,
                    LatencyEvent.duration_ms,
                    LatencyEvent.host_class,
                ).where(LatencyEvent.session_id == session.id)
            )
        ).all()
        persona_model = (
            await db.execute(
                select(ModelCall.model)
                .where(ModelCall.session_id == session.id, ModelCall.role == "persona")
                .limit(1)
            )
        ).scalar_one_or_none()

    ordered = sorted(
        turns, key=lambda t: (t.start_ms, 0 if t.speaker == "persona" and t.index < 0 else 1)
    )
    speakers = [t.speaker for t in ordered]
    seg_speakers = [s["speaker"] for s in segments]
    if speakers != seg_speakers:
        raise SystemExit(
            f"turn/segment mismatch:\n  turns    {speakers}\n  segments {seg_speakers}"
        )

    latency: dict[str, dict[str, float]] = {}
    host_class = None
    for turn_id, stage, duration_ms, host in latency_rows:
        latency.setdefault(str(turn_id), {})[stage] = round(duration_ms)
        host_class = host_class or host

    turn_json = []
    for turn, seg in zip(ordered, segments, strict=True):
        data = turn.model_dump(mode="json")
        data["start_ms"] = int(seg["start_ms"])
        data["end_ms"] = int(seg["end_ms"])
        turn_json.append(data)

    session_json = session_service.session_to_out(session).model_dump(mode="json")
    session_json["duration_ms"] = int(capture["duration_ms"])
    session_json["recording_available"] = True

    timeline_wav = RAW_DIR / f"{session_id}_timeline.wav"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603, S607, ASYNC221 — fixed argv; one-off export script, not a server
        [  # noqa: S607 — ffmpeg from PATH, as in generate_audio_fixtures.py
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(timeline_wav),
            "-ac",
            "1",
            "-b:a",
            "48k",
            str(OUT_DIR / "sample-session.mp3"),
        ],
        check=True,
    )

    bundle = {
        "provenance": {
            "session_id": session_id,
            "recorded_at": session.created_at.isoformat(),
            "exported_at": datetime.now(UTC).isoformat(),
            "host_class": host_class,
            "persona_model": persona_model,
            "scorer_model_version": next(
                (
                    s["model_version"]
                    for t in turn_json
                    for s in t["scores"]
                    if s["criterion_key"] != "delivery"
                ),
                None,
            ),
            "voices": {
                "user": "Piper en_GB-alan-medium (scripted answers, synthesized)",
                "persona": f"Piper {persona.voice_id if persona else 'unknown'} (live pipeline)",
            },
            "note": (
                "Recorded through the real realtime service and scored by the real coach worker. "
                "The user's answers are scripted and synthesized; nothing else was edited."
            ),
        },
        "session": session_json,
        "scenario": scenario
        and {
            "id": str(scenario.id),
            "slug": scenario.slug,
            "family": scenario.family,
            "difficulty": scenario.difficulty,
            "title": scenario.title,
            "brief": scenario.brief,
            "opening_strategy": scenario.opening_strategy,
            "duration_minutes": scenario.duration_minutes,
            "tags": scenario.tags,
            "persona_id": str(scenario.persona_id) if scenario.persona_id else None,
            "rubric_id": str(scenario.rubric_id) if scenario.rubric_id else None,
        },
        "turns": turn_json,
        "scores": [s.model_dump(mode="json") for s in scores],
        "report": session_service.report_to_out(report).model_dump(mode="json"),
        "recording": {
            "url": "/demo/sample-session.mp3",
            "format": None,  # mp3 for size; the player only needs the URL
            "peaks": _peaks(timeline_wav),
            "duration_ms": int(capture["duration_ms"]),
        },
        "latency_by_turn": latency,
    }
    (OUT_DIR / "sample-session.json").write_text(json.dumps(bundle, indent=1), encoding="utf-8")
    print(f"wrote {OUT_DIR / 'sample-session.json'} and sample-session.mp3")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    asyncio.run(export(parser.parse_args().session_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
