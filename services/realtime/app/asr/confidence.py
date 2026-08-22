"""Confidence gating (Task 1.4, SP-08). Below threshold, the transcript is not trusted enough
to send to the persona as-is — a confidently wrong reply to a misheard question is worse than
asking again. Clarification lines are content, not code (CLAUDE.md §2, §11) — see
content/clarifications.yaml.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIDENCE_THRESHOLD = 0.55

_DEFAULT_PATH = Path(__file__).resolve().parents[4] / "content" / "clarifications.yaml"


def is_confident(asr_confidence: float) -> bool:
    return asr_confidence >= CONFIDENCE_THRESHOLD


def load_clarification_pool(path: Path = _DEFAULT_PATH) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    lines: list[str] = data["lines"]
    if not lines:
        raise ValueError(f"{path} has no clarification lines")
    return lines


def pick_clarification(pool: list[str], turn_index: int) -> str:
    """Cycles through the pool so a session doesn't repeat the exact same line every time."""
    return pool[turn_index % len(pool)]
