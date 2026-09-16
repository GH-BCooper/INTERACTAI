#!/usr/bin/env python3
# ruff: noqa: E501 — metric tables in the docstring and one-line markdown summaries.
"""Publishes the numbers the landing page and README show — Phase 6 TASK 6.6/6.7.

Every figure is read from an `eval_runs` row (or, for live latency, `latency_events`) and carries
its row id, dataset revision, model version and date. A metric with no row is written as
`null` and rendered as "not yet measured" — never a placeholder (CLAUDE.md §10).

Usage:
    uv run python scripts/publish_metrics.py              # writes apps/web/public/published-metrics.json
    uv run python scripts/publish_metrics.py --markdown   # prints a markdown summary (CI job summary)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

OUT = REPO_ROOT / "apps" / "web" / "public" / "published-metrics.json"


def _run(row: Any) -> dict[str, Any]:
    return {
        "eval_run_id": str(row.id),
        "configuration": row.configuration,
        "dataset_revision": row.dataset_revision_hash,
        "prompt_version": row.prompt_version,
        "host_class": row.host_class,
        "date": row.created_at.date().isoformat(),
        "metrics": row.metrics,
        "qwk": row.qwk,
        "split": row.split,
        "published": row.published,
    }


async def collect() -> dict[str, Any]:
    from sqlalchemy import desc, select

    from app.core.db import get_sessionmaker
    from app.models import EvalRun

    async with get_sessionmaker()() as db:

        async def latest(suite: str, **filters: Any) -> Any:
            stmt = select(EvalRun).where(EvalRun.suite == suite).order_by(desc(EvalRun.created_at))
            for rows in (await db.execute(stmt)).scalars().all():
                if all(filters.get(k) is None or getattr(rows, k) == v for k, v in filters.items()):
                    if "BROKEN" not in (rows.configuration or ""):
                        return rows
            return None

        speech = await latest("speech")
        persona = await latest("persona")
        scorer_rows = (
            (
                await db.execute(
                    select(EvalRun)
                    .where(
                        EvalRun.suite.notin_(["speech", "persona"]),
                        EvalRun.split == "test",
                        EvalRun.published.is_(True),
                    )
                    .order_by(desc(EvalRun.created_at))
                )
            )
            .scalars()
            .all()
        )
        ceiling = next((r for r in scorer_rows if r.configuration == "human_ceiling"), None)
        best_model = next(
            (r for r in scorer_rows if r.configuration != "human_ceiling" and r.qwk is not None),
            None,
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "latency": speech
        and {
            **_run(speech),
            "p50_ms": speech.metrics.get("ttfa_p50_ms"),
            "p90_ms": speech.metrics.get("ttfa_p90_ms"),
            "p95_ms": speech.metrics.get("ttfa_p95_ms"),
            "n": speech.metrics.get("ttfa_n"),
            "target_p95_ms": 1400,
        },
        "speech": speech and _run(speech),
        "persona": persona and _run(persona),
        "scorer": best_model and _run(best_model),
        "human_ceiling": ceiling and _run(ceiling),
    }


def to_markdown(data: dict[str, Any]) -> str:
    def v(x: Any) -> str:
        return "not yet measured" if x is None else str(x)

    lines = ["## Evaluation metrics", ""]
    lat, sp, pe = data.get("latency"), data.get("speech"), data.get("persona")
    if lat:
        lines.append(
            f"**Latency (e2e, {lat['host_class']}, {lat['date']}, n={v(lat['n'])})** — p50 {v(lat['p50_ms'])} ms · p90 {v(lat['p90_ms'])} ms · p95 {v(lat['p95_ms'])} ms (target p95 ≤ 1400 ms)"
        )
    if sp:
        m = sp["metrics"]
        lines.append(
            f"**Speech ({sp['configuration']}, rev `{sp['dataset_revision'][:10]}`, {sp['date']})** — WER {v(m.get('wer_overall'))} (accented {v(m.get('wer_accented'))}, technical {v(m.get('wer_technical'))}) · ASR RTF {v(m.get('asr_rtf'))} · TTS RTF {v(m.get('tts_rtf'))} · endpoint precision {v(m.get('endpoint_precision'))} / recall {v(m.get('endpoint_recall'))} · passed {m.get('passed')}"
        )
    else:
        lines.append("**Speech** — not yet measured")
    if pe:
        m = pe["metrics"]
        lines.append(
            f"**Persona ({pe['configuration']}, rev `{pe['dataset_revision'][:10]}`, {pe['date']})** — character break rate {v(m.get('character_break_rate'))} · repetitions {v(m.get('question_repetitions'))} · plan adherence {v(m.get('plan_adherence'))} · mean reply {v(m.get('turn_length_mean_words'))} words · separation {m.get('difficulty_separation', {}).get('p_values')} · passed {m.get('passed')}"
        )
    else:
        lines.append("**Persona** — not yet measured")
    sc, hc = data.get("scorer"), data.get("human_ceiling")
    lines.append(
        f"**Scorer agreement (published test split)** — QWK {v(sc and sc['qwk'])} vs human ceiling {v(hc and hc['qwk'])}"
    )
    return "\n\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    try:
        data = asyncio.run(collect())
    except Exception as exc:  # noqa: BLE001
        print(f"no metrics database reachable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if args.markdown:
        print(to_markdown(data))
    else:
        OUT.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
