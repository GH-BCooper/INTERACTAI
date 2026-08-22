#!/usr/bin/env python3
"""Runs the evaluation suites and writes an eval_runs row (docs/19-build-plan.md, day 18+).

Not built yet — the eval_runs table doesn't exist until day 18 (docs/phase-0-BUILD.md TASK 0.4
explicitly says not to create it speculatively in Phase 0). `make eval` exists as a target now
so the Makefile's target list is stable across phases.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "make eval: not implemented yet - arrives in Phase 5 alongside eval_runs "
        "(docs/phase-5-BUILD.md).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
