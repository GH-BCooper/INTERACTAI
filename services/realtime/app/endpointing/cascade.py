"""The endpointing cascade (Task 1.3b) — the highest-leverage code in the system
(docs/phase-1-LEARN.md §4). `should_endpoint` is the pure, synchronous cascade (steps 1-4);
`resolve_endpoint` is the thin async wrapper that adds step 5 (the only step allowed I/O), so
the 15+ unit tests below can exercise steps 1-4 with zero mocking.

Cascade, cheapest first:
  1+2. Acoustic silence vs. a threshold — base, or adaptive per speaker (AdaptiveThresholdTracker
       below) once >=3 utterances have been observed this session.
  3+4. Filler / syntactic-incompleteness suppression — regex against the transcript tail,
       extending the window, capped at MAX_EXTENSIONS_PER_UTTERANCE total (not per-rule).
  5.   Semantic completeness check — only when the window elapsed and steps 3-4 still flag the
       transcript unfinished but the extension budget is spent. 80ms hard timeout; on timeout,
       END (a slightly early cut beats an unbounded wait).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum, auto

BASE_SILENCE_MS = 500.0
MIN_SILENCE_MS = 350.0
MAX_SILENCE_MS = 900.0
MIN_UTTERANCE_MS = 400.0
MAX_TURN_MS = 120_000.0
SEMANTIC_TIMEOUT_MS = 80.0

FILLER_EXTENSION_MS = 300.0
SYNTAX_EXTENSION_MS = 250.0
MAX_EXTENSIONS_PER_UTTERANCE = 2

# Hesitation markers — a config constant per Task 1.4's own convention for the filler list;
# kept here (not imported from asr) since this list's purpose (extend the endpoint window) is
# distinct from Task 1.4's delivery-metrics filler list, even though the words overlap.
FILLER_TAIL_RE = re.compile(r"\b(um|uh|erm|hmm|so|like|and|but|you know|i mean)\s*$", re.IGNORECASE)
# Trailing coordinating conjunction, preposition or article — "I worked on the—" ending in
# "the" is almost never a finished sentence (docs/phase-1-LEARN.md §4).
INCOMPLETE_TAIL_RE = re.compile(
    r"\b(and|but|or|so|because|the|a|an|to|of|in|on|at|with|for|as|nor|yet)\s*$",
    re.IGNORECASE,
)


class EndpointDecision(Enum):
    END = auto()
    CONTINUE = auto()
    NEEDS_SEMANTIC_CHECK = auto()


@dataclass
class EndpointState:
    silence_ms: float
    utterance_duration_ms: float
    threshold_ms: float
    transcript_tail: str = ""
    extensions_used: int = 0


def should_endpoint(state: EndpointState) -> EndpointDecision:
    """Pure and synchronous — steps 1-4 only. Mutates `state.threshold_ms`/`extensions_used`
    in place when granting an extension; that bookkeeping is local to the caller's own state
    object, not global or I/O, so this stays fully deterministic and side-effect-free w.r.t.
    the outside world."""
    if state.utterance_duration_ms >= MAX_TURN_MS:
        return EndpointDecision.END

    if state.silence_ms < state.threshold_ms:
        return EndpointDecision.CONTINUE

    flagged_unfinished = bool(
        FILLER_TAIL_RE.search(state.transcript_tail)
        or INCOMPLETE_TAIL_RE.search(state.transcript_tail)
    )

    if flagged_unfinished and state.extensions_used < MAX_EXTENSIONS_PER_UTTERANCE:
        extension = (
            FILLER_EXTENSION_MS
            if FILLER_TAIL_RE.search(state.transcript_tail)
            else SYNTAX_EXTENSION_MS
        )
        state.threshold_ms += extension
        state.extensions_used += 1
        return EndpointDecision.CONTINUE

    if flagged_unfinished:
        return EndpointDecision.NEEDS_SEMANTIC_CHECK

    return EndpointDecision.END


SemanticChecker = Callable[[str], Awaitable[bool]]
"""Returns True if the transcript looks complete. Implemented in Task 1.6 against
MODEL_ENDPOINTER via litellm; kept as an injected callable here so the timeout/fallback path
is testable without a real model call."""


async def resolve_endpoint(
    state: EndpointState,
    semantic_checker: SemanticChecker | None,
    *,
    timeout_ms: float = SEMANTIC_TIMEOUT_MS,
) -> EndpointDecision:
    """The only place step 5 (and its 80ms budget) lives. Always returns END or CONTINUE —
    never NEEDS_SEMANTIC_CHECK, which is purely an internal signal from `should_endpoint`."""
    import asyncio

    decision = should_endpoint(state)
    if decision is not EndpointDecision.NEEDS_SEMANTIC_CHECK:
        return decision

    if semantic_checker is None:
        return EndpointDecision.END  # component unavailable — cuttable, per Task 1.3c cut order

    try:
        is_complete = await asyncio.wait_for(
            semantic_checker(state.transcript_tail), timeout=timeout_ms / 1000
        )
    except TimeoutError:
        return EndpointDecision.END  # slightly early cut beats an unbounded wait

    return EndpointDecision.END if is_complete else EndpointDecision.CONTINUE


def is_utterance_too_short(utterance_duration_ms: float) -> bool:
    """Task 1.3c guard: a detection shorter than this is noise (cough, door slam) — discard,
    no turn, state returns to idle."""
    return utterance_duration_ms < MIN_UTTERANCE_MS


def exceeds_max_turn_length(utterance_duration_ms: float) -> bool:
    """Task 1.3c guard: the caller uses this to log `persona_interrupt` rather than a normal
    endpoint when `should_endpoint` returns END for this reason."""
    return utterance_duration_ms >= MAX_TURN_MS


@dataclass
class AdaptiveThresholdTracker:
    """Task 1.3b step 2. Tracks the distribution of within-utterance pauses observed so far
    this session and derives a per-speaker silence threshold from their ~90th percentile,
    clamped to [MIN_SILENCE_MS, MAX_SILENCE_MS]. Falls back to BASE_SILENCE_MS until at least
    `min_utterances` utterances have completed."""

    base_ms: float = BASE_SILENCE_MS
    min_ms: float = MIN_SILENCE_MS
    max_ms: float = MAX_SILENCE_MS
    min_utterances: int = 3
    _pauses_ms: list[float] = field(default_factory=list)
    _utterances_completed: int = 0

    def record_utterance(self, internal_pause_durations_ms: list[float]) -> None:
        """Call once per completed utterance with every internal (non-endpointing) pause
        observed during it — the gaps VAD saw that didn't cross the threshold in force."""
        self._pauses_ms.extend(internal_pause_durations_ms)
        self._utterances_completed += 1

    def current_threshold_ms(self) -> float:
        if self._utterances_completed < self.min_utterances or not self._pauses_ms:
            return self.base_ms
        p90 = _percentile(self._pauses_ms, 90)
        return min(max(p90, self.min_ms), self.max_ms)


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    lower, upper = int(rank), min(int(rank) + 1, len(ordered) - 1)
    frac = rank - lower
    return ordered[lower] + frac * (ordered[upper] - ordered[lower])
