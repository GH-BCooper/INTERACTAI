"""Deterministic delivery metrics (Task 1.4, SP-10). Computed from word timings only, never
from a model — CLAUDE.md §5: `turn_metrics` is arithmetic on timestamps and is always correct.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# Config constant, not inline (Task 1.4). Multi-word entries are matched as consecutive
# standalone tokens, not substrings.
FILLER_WORDS = (
    "um",
    "uh",
    "erm",
    "ah",
    "like",
    "you know",
    "i mean",
    "sort of",
    "kind of",
    "basically",
    "actually",
    "literally",
)

_SINGLE_TOKEN_FILLERS = frozenset(f for f in FILLER_WORDS if " " not in f)
_MULTI_TOKEN_FILLERS = frozenset(tuple(f.split(" ")) for f in FILLER_WORDS if " " in f)

_NON_WORD_RE = re.compile(r"[^\w']")


class WordTimingLike(Protocol):
    """Structural, read-only — matches both plain objects and frozen dataclasses like
    `asr.whisper.WordTiming`."""

    @property
    def word(self) -> str: ...
    @property
    def start_ms(self) -> int: ...
    @property
    def end_ms(self) -> int: ...


@dataclass(frozen=True, slots=True)
class DeliveryMetrics:
    wpm: float
    filler_count: int
    filler_rate: float
    longest_pause_ms: int
    speech_ratio: float
    word_count: int


def _normalize_token(word: str) -> str:
    return _NON_WORD_RE.sub("", word).strip().lower()


def _count_fillers(tokens: list[str]) -> int:
    """Standalone-token matching only (Task 1.4): "like" is counted only as its own token, not
    wherever the substring "like" appears (e.g. inside "unlike" or "liked"). This does not
    disambiguate a filler "like" from a comparative one ("a system like Kafka") — that would
    need semantic context a token-boundary check can't provide; it is a known, accepted
    limitation of a purely deterministic metric."""
    count = 0
    i = 0
    n = len(tokens)
    while i < n:
        if i + 1 < n and (tokens[i], tokens[i + 1]) in _MULTI_TOKEN_FILLERS:
            count += 1
            i += 2
            continue
        if tokens[i] in _SINGLE_TOKEN_FILLERS:
            count += 1
        i += 1
    return count


def compute_delivery_metrics(
    words: Sequence[WordTimingLike], *, utterance_start_ms: int, utterance_end_ms: int
) -> DeliveryMetrics:
    word_count = len(words)
    duration_ms = max(utterance_end_ms - utterance_start_ms, 1)

    tokens = [_normalize_token(w.word) for w in words]
    filler_count = _count_fillers(tokens)
    filler_rate = filler_count / word_count if word_count else 0.0

    wpm = (word_count / duration_ms) * 60_000

    longest_pause_ms = 0
    speech_ms = 0
    prev_end = utterance_start_ms
    for w in words:
        gap = w.start_ms - prev_end
        longest_pause_ms = max(longest_pause_ms, gap)
        speech_ms += max(w.end_ms - w.start_ms, 0)
        prev_end = w.end_ms
    longest_pause_ms = max(longest_pause_ms, utterance_end_ms - prev_end)

    speech_ratio = min(speech_ms / duration_ms, 1.0) if duration_ms else 0.0

    return DeliveryMetrics(
        wpm=wpm,
        filler_count=filler_count,
        filler_rate=filler_rate,
        longest_pause_ms=max(longest_pause_ms, 0),
        speech_ratio=speech_ratio,
        word_count=word_count,
    )
