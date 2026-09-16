"""Shared plumbing for the Level 1 and Level 2 evaluation suites (Phase 6 TASK 6.3).

Every suite run writes one `eval_runs` row, attributable to an exact input set: the fixture
content is hashed into a `dataset_revisions` row (created on first use), so a metric is never
reported without the inputs that produced it (CLAUDE.md §10).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"


def hash_inputs(paths: list[Path], extra: dict[str, Any] | None = None) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    if extra is not None:
        digest.update(json.dumps(extra, sort_keys=True).encode())
    return digest.hexdigest()[:40]


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (pct / 100) * (len(ordered) - 1)
    lo, hi = int(math.floor(rank)), int(math.ceil(rank))
    return ordered[lo] + (rank - lo) * (ordered[hi] - ordered[lo])


_WORD = re.compile(r"[a-z0-9']+")
_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


def normalize_words(text: str) -> list[str]:
    """Lower-case, punctuation-free tokens with spelled small numbers folded to digits, so
    "ten" vs "10" is not counted as an ASR error (a formatting choice, not a recognition one)."""
    return [_NUMBER_WORDS.get(w, w) for w in _WORD.findall(text.lower())]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def use_api_app() -> None:
    """services/api and services/realtime both expose a top-level `app` package (see
    scripts/cli.py's note and docs/decisions/0003). A suite that has already imported realtime's
    `app` must evict it before touching the API models, or `app.core.db` resolves to the wrong
    service."""
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]
    realtime_dir = str(REPO_ROOT / "services" / "realtime")
    sys.path[:] = [p for p in sys.path if p != realtime_dir]
    for p in (str(API_DIR), str(REPO_ROOT)):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


async def write_eval_run(
    *,
    suite: str,
    configuration: str,
    revision_hash: str,
    revision_notes: str,
    metrics: dict[str, Any],
    host_class: str | None,
    prompt_version: str | None = None,
) -> str | None:
    """Returns the eval_runs id, or None when no database is reachable (CI without Postgres):
    the suite's pass/fail verdict never depends on being able to record it."""
    use_api_app()
    try:
        from app.core.db import get_sessionmaker
        from app.models import DatasetRevision, EvalRun

        async with get_sessionmaker()() as db:
            if await db.get(DatasetRevision, revision_hash) is None:
                db.add(
                    DatasetRevision(
                        hash=revision_hash,
                        turn_count=0,
                        label_count=0,
                        speaker_count=0,
                        source_breakdown={},
                        split_counts={},
                        excluded_turn_ids=[],
                        notes=revision_notes,
                    )
                )
                await db.flush()
            run = EvalRun(
                suite=suite,
                configuration=configuration,
                prompt_version=prompt_version,
                metrics=metrics,
                host_class=host_class,
                dataset_revision_hash=revision_hash,
                split="validation",
                per_criterion={},
            )
            db.add(run)
            await db.commit()
            return str(run.id)
    except Exception as exc:  # noqa: BLE001 — recording is best-effort, the verdict is not
        print(f"  (eval_runs row not written: {type(exc).__name__}: {exc})")
        return None
