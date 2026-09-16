#!/usr/bin/env python3
# ruff: noqa: E501 — metric tables in the docstring and one-line markdown summaries.
"""Level 1 — speech components (Phase 6 TASK 6.3a). `make eval-speech`.

| Metric                  | Source                                                          |
|-------------------------|-----------------------------------------------------------------|
| WER (clean/accented/technical) | tests/fixtures/audio/manifest.json, real faster-whisper   |
| ASR real-time factor    | wall-clock transcribe time / audio duration, per host class      |
| Endpoint precision      | of ends called, fraction at/after the labelled true end          |
| Endpoint recall+latency | data/boundaries/labels.jsonl (220 marked boundaries), if present |
| Time to first audio     | latency_events stage='e2e' for this host class, if a DB is up    |
| Synthesis RTF           | Piper synth time / produced audio duration                       |

Hard gates (exit 1, never a warning): ASR RTF > 1.0 or synthesis RTF > 1.0 — above 1.0 the
design fails. WER, precision and recall are reported, not gated: their thresholds are a product
decision still to be made against real speech (see docs/decisions/0022).

Deterministic: fixed fixtures, beam search with temperature 0, VAD/cascade are pure functions of
the audio. Timing-derived numbers (RTF, TTFA) vary with the host, which is why they are keyed by
HOST_CLASS.

Usage: uv run python scripts/eval_speech.py [--skip-endpointing] [--no-db]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import wave
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from scripts.eval_common import (  # noqa: E402
    hash_inputs,
    percentile,
    use_api_app,
    word_error_rate,
    write_eval_run,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "audio"
MANIFEST = FIXTURES / "manifest.json"
BOUNDARY_LABELS = REPO_ROOT / "data" / "boundaries" / "labels.jsonl"
RTF_LIMIT = 1.0


def _duration_s(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def rtf_gate(name: str, rtf: float | None, limit: float = RTF_LIMIT) -> str | None:
    """Returns a failure message when the real-time factor breaks the design, else None."""
    if rtf is not None and rtf > limit:
        return f"{name} real-time factor {rtf:.3f} > {limit} — the design fails on this host"
    return None


def run_asr(manifest: dict[str, Any], model_name: str) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    # Warm-up pass so the first fixture's RTF does not include one-off graph initialisation.
    list(model.transcribe(str(FIXTURES / manifest["items"][0]["file"]), beam_size=1)[0])

    by_group: dict[str, list[float]] = {}
    per_item = []
    audio_s = decode_s = 0.0
    for item in manifest["items"]:
        path = FIXTURES / item["file"]
        t0 = time.perf_counter()
        segments, _ = model.transcribe(
            str(path), beam_size=5, temperature=0.0, condition_on_previous_text=False
        )
        text = " ".join(s.text.strip() for s in segments)
        elapsed = time.perf_counter() - t0
        duration = _duration_s(path)
        audio_s += duration
        decode_s += elapsed
        wer = word_error_rate(item["reference"], text)
        by_group.setdefault(item["group"], []).append(wer)
        per_item.append(
            {
                "file": item["file"],
                "group": item["group"],
                "wer": round(wer, 4),
                "hypothesis": text,
                "rtf": round(elapsed / duration, 4),
            }
        )
        print(f"  {item['file']:<32} WER {wer:.3f}  RTF {elapsed / duration:.3f}  «{text}»")

    all_wers = [w for ws in by_group.values() for w in ws]
    return {
        "wer_overall": round(sum(all_wers) / len(all_wers), 4),
        **{f"wer_{g}": round(sum(ws) / len(ws), 4) for g, ws in by_group.items()},
        "asr_rtf": round(decode_s / audio_s, 4),
        "asr_model": model_name,
        "per_item": per_item,
    }


def run_tts(manifest: dict[str, Any], voice_id: str) -> dict[str, Any]:
    sys.path.insert(0, str(REPO_ROOT / "services" / "realtime"))
    from app.tts.piper import VoicePool

    pool = VoicePool(REPO_ROOT / "models" / "piper")
    voice = pool.get(voice_id)
    list(voice.synthesize("Warm up."))
    synth_s = audio_s = 0.0
    for text in manifest["tts_texts"]:
        t0 = time.perf_counter()
        chunks = [c.audio_float_array for c in voice.synthesize(text)]
        synth_s += time.perf_counter() - t0
        audio_s += sum(len(c) for c in chunks) / voice.config.sample_rate
    return {"tts_rtf": round(synth_s / audio_s, 4), "tts_voice": voice_id}


def run_endpointing(limit: int | None) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from eval_endpointing import (  # type: ignore[import-not-found]
        _load_pcm,
        _transcribe_words,
        load_vad_session,
        simulate_endpointing,
    )

    items = [
        json.loads(line)
        for line in BOUNDARY_LABELS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    items = [i for i in items if (REPO_ROOT / i["audio_path"]).exists()][:limit]
    if not items:
        return {}
    vad = load_vad_session(str(REPO_ROOT / "models" / "vad" / "silero_vad.onnx"))
    asr = WhisperModel("base.en", device="cpu", compute_type="int8")
    called = correct = 0
    latencies: list[float] = []
    for item in items:
        path = REPO_ROOT / item["audio_path"]
        declared = simulate_endpointing(_load_pcm(path), _transcribe_words(asr, path), vad)
        if declared is None:
            continue
        called += 1
        if declared >= float(item["true_end_ms"]):
            correct += 1
            latencies.append(declared - float(item["true_end_ms"]))
    return {
        "endpoint_items": len(items),
        "endpoint_precision": round(correct / called, 4) if called else None,
        # Same definitions as scripts/eval_endpointing.py (Phase 1): recall = boundaries where an
        # end was called at all; precision = of those, called at/after the true end (not early).
        "endpoint_recall": round(called / len(items), 4),
        "endpoint_latency_p50_ms": percentile(latencies, 50),
        "endpoint_latency_p95_ms": percentile(latencies, 95),
        "endpoint_labels": "data/boundaries/labels.jsonl (synthetic Piper speech, hand-marked true ends)",
    }


async def ttfa_from_db(host_class: str) -> dict[str, Any]:
    use_api_app()
    try:
        from sqlalchemy import select

        from app.core.db import get_sessionmaker
        from app.models import LatencyEvent

        async with get_sessionmaker()() as db:
            rows = (
                (
                    await db.execute(
                        select(LatencyEvent.duration_ms).where(
                            LatencyEvent.stage == "e2e", LatencyEvent.host_class == host_class
                        )
                    )
                )
                .scalars()
                .all()
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  (time-to-first-audio not measured: {type(exc).__name__}: {exc})")
        return {}
    values = [float(v) for v in rows]
    if not values:
        return {}
    return {
        "ttfa_n": len(values),
        "ttfa_p50_ms": round(percentile(values, 50) or 0),
        "ttfa_p90_ms": round(percentile(values, 90) or 0),
        "ttfa_p95_ms": round(percentile(values, 95) or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--asr-model", default=os.environ.get("ASR_MODEL", "base.en"))
    parser.add_argument("--voice", default="en_US-lessac-medium")
    parser.add_argument("--skip-endpointing", action="store_true")
    parser.add_argument("--endpointing-limit", type=int, default=None)
    parser.add_argument("--no-db", action="store_true")
    parser.add_argument("--rtf-limit", type=float, default=RTF_LIMIT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    host_class = os.environ.get("HOST_CLASS", "unspecified")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    print(f"Level 1 speech suite · host_class={host_class}")
    metrics: dict[str, Any] = {"host_class": host_class}
    metrics.update(run_asr(manifest, args.asr_model))
    metrics.update(run_tts(manifest, args.voice))
    if not args.skip_endpointing and BOUNDARY_LABELS.exists():
        print("  endpointing against labelled boundaries…")
        metrics.update(run_endpointing(args.endpointing_limit))
    if not args.no_db:
        metrics.update(asyncio.run(ttfa_from_db(host_class)))

    failures = [
        f
        for f in (
            rtf_gate("ASR", metrics["asr_rtf"], args.rtf_limit),
            rtf_gate("Synthesis", metrics["tts_rtf"], args.rtf_limit),
        )
        if f
    ]
    metrics["passed"] = not failures

    summary = {k: v for k, v in metrics.items() if k != "per_item"}
    print(json.dumps(summary, indent=2))

    if not args.no_db:
        wavs = [FIXTURES / i["file"] for i in manifest["items"]]
        revision = hash_inputs(wavs, {"manifest": manifest})
        run_id = asyncio.run(
            write_eval_run(
                suite="speech",
                configuration=f"asr={args.asr_model};tts={args.voice}",
                revision_hash=revision,
                revision_notes=f"Level 1 speech fixtures v{manifest['version']} (tests/fixtures/audio)",
                metrics=metrics,
                host_class=host_class,
            )
        )
        if run_id:
            print(f"  eval_runs row {run_id} · dataset revision {revision}")

    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
