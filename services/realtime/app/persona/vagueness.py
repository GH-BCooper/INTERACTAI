"""Feeds docs/phase-2-BUILD.md TASK 2.3b's "advance on a strong answer, increment
followups_used on a vague one." A cheap, deterministic heuristic reusing metrics
`asr.delivery_metrics.compute_delivery_metrics` already computes for Task 1.4/2.5a — no extra
model call, consistent with this codebase's preference for free, always-correct signals over a
judgement call that would need its own verification.
"""

from __future__ import annotations

MIN_SUBSTANTIVE_WORDS = 15
HIGH_FILLER_RATE = 0.15


def is_answer_vague(*, word_count: int, filler_rate: float) -> bool:
    """A short answer, or one that's mostly filler, reads as vague regardless of its exact
    content — this is deliberately a coarse, cheap proxy, not a claim about semantic content."""
    return word_count < MIN_SUBSTANTIVE_WORDS or filler_rate >= HIGH_FILLER_RATE
