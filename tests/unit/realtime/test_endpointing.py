"""Task 1.3 acceptance: "The cascade is a pure function with >= 15 unit tests covering every
row [of the edge-case table]." One test class per concern; every edge-case-table row has an
explicit test, named after the row.
"""

from __future__ import annotations

import asyncio

import pytest

from services.realtime.app.endpointing.cascade import (
    FILLER_EXTENSION_MS,
    MAX_EXTENSIONS_PER_UTTERANCE,
    MAX_TURN_MS,
    MIN_UTTERANCE_MS,
    SYNTAX_EXTENSION_MS,
    AdaptiveThresholdTracker,
    EndpointDecision,
    EndpointState,
    exceeds_max_turn_length,
    is_utterance_too_short,
    resolve_endpoint,
    should_endpoint,
)


def _state(
    *,
    silence_ms: float = 0.0,
    utterance_duration_ms: float = 1000.0,
    threshold_ms: float = 500.0,
    transcript_tail: str = "",
    extensions_used: int = 0,
) -> EndpointState:
    return EndpointState(
        silence_ms=silence_ms,
        utterance_duration_ms=utterance_duration_ms,
        threshold_ms=threshold_ms,
        transcript_tail=transcript_tail,
        extensions_used=extensions_used,
    )


# ── 1. Below threshold: keep listening ──────────────────────────────────────────────────────
def test_silence_below_threshold_continues() -> None:
    state = _state(silence_ms=100.0, threshold_ms=500.0)
    assert should_endpoint(state) is EndpointDecision.CONTINUE


def test_silence_at_threshold_boundary_ends() -> None:
    state = _state(silence_ms=500.0, threshold_ms=500.0, transcript_tail="that's my answer")
    assert should_endpoint(state) is EndpointDecision.END


# ── 2. Threshold reached, transcript complete: end ──────────────────────────────────────────
def test_threshold_reached_no_filler_or_syntax_ends() -> None:
    state = _state(
        silence_ms=600.0, threshold_ms=500.0, transcript_tail="that is the final answer."
    )
    assert should_endpoint(state) is EndpointDecision.END


# ── 3. Filler suppression grants an extension ───────────────────────────────────────────────
def test_filler_tail_extends_window() -> None:
    state = _state(silence_ms=600.0, threshold_ms=500.0, transcript_tail="so I was thinking, um")
    assert should_endpoint(state) is EndpointDecision.CONTINUE
    assert state.threshold_ms == 500.0 + FILLER_EXTENSION_MS
    assert state.extensions_used == 1


@pytest.mark.parametrize("filler", ["um", "uh", "erm", "hmm", "so", "like", "you know", "I mean"])
def test_every_documented_filler_marker_triggers_extension(filler: str) -> None:
    state = _state(silence_ms=600.0, threshold_ms=500.0, transcript_tail=f"and then, {filler}")
    assert should_endpoint(state) is EndpointDecision.CONTINUE
    assert state.extensions_used == 1


# ── 4. Syntactic incompleteness grants an extension ─────────────────────────────────────────
def test_trailing_conjunction_extends_window() -> None:
    state = _state(silence_ms=600.0, threshold_ms=500.0, transcript_tail="I worked on the")
    assert should_endpoint(state) is EndpointDecision.CONTINUE
    assert state.threshold_ms == 500.0 + SYNTAX_EXTENSION_MS
    assert state.extensions_used == 1


def test_trailing_preposition_extends_window() -> None:
    state = _state(silence_ms=600.0, threshold_ms=500.0, transcript_tail="I handed it off to")
    assert should_endpoint(state) is EndpointDecision.CONTINUE


# ── Extension cap: prevents unbounded holding ───────────────────────────────────────────────
def test_extension_cap_stops_after_two_grants() -> None:
    state = _state(silence_ms=600.0, threshold_ms=500.0, transcript_tail="so, um")
    for _ in range(MAX_EXTENSIONS_PER_UTTERANCE):
        assert should_endpoint(state) is EndpointDecision.CONTINUE
        state.silence_ms = state.threshold_ms  # simulate silence catching back up
    assert state.extensions_used == MAX_EXTENSIONS_PER_UTTERANCE
    # a third still-unfinished-looking tail no longer gets a free extension
    result = should_endpoint(state)
    assert result is EndpointDecision.NEEDS_SEMANTIC_CHECK


def test_extension_cap_exhausted_with_complete_tail_ends_directly() -> None:
    state = _state(
        silence_ms=600.0,
        threshold_ms=500.0,
        transcript_tail="that's it",
        extensions_used=MAX_EXTENSIONS_PER_UTTERANCE,
    )
    assert should_endpoint(state) is EndpointDecision.END


# ── Row: "Speaker says 'um...' and stops for 2s -> ends after cap, not forever" ─────────────
def test_um_then_silence_ends_after_extension_cap_via_semantic_timeout() -> None:
    state = _state(silence_ms=500.0, threshold_ms=500.0, transcript_tail="I think, um")
    # First two threshold hits both extend (filler match).
    for _ in range(MAX_EXTENSIONS_PER_UTTERANCE):
        assert should_endpoint(state) is EndpointDecision.CONTINUE
        state.silence_ms = state.threshold_ms
    # Now the 2-second stall has caught silence back up to the (twice-extended) threshold, and
    # no more extensions are available -> falls to the semantic check, which is unreachable.
    assert should_endpoint(state) is EndpointDecision.NEEDS_SEMANTIC_CHECK

    async def _run() -> EndpointDecision:
        return await resolve_endpoint(state, semantic_checker=None)

    assert asyncio.run(_run()) is EndpointDecision.END


# ── Row: "Speaker pauses 800ms mid-sentence -> adaptive threshold + syntax rule should hold" ─
def test_mid_sentence_800ms_pause_held_by_adaptive_threshold_and_syntax() -> None:
    adaptive_threshold_ms = 850.0  # e.g. this speaker's own p90, clamped within [350, 900]
    state = _state(
        silence_ms=800.0, threshold_ms=adaptive_threshold_ms, transcript_tail="I built the"
    )
    # 800ms < the adaptive 850ms threshold alone already holds...
    assert should_endpoint(state) is EndpointDecision.CONTINUE

    # ...and even if the threshold were lower, the trailing article extends it further.
    state2 = _state(silence_ms=800.0, threshold_ms=500.0, transcript_tail="I built the")
    assert should_endpoint(state2) is EndpointDecision.CONTINUE
    assert state2.threshold_ms == 500.0 + SYNTAX_EXTENSION_MS
    assert state2.extensions_used == 1


# ── Row: "Continuous background noise -> max turn length fires" ────────────────────────────
def test_max_turn_length_forces_end_regardless_of_silence() -> None:
    state = _state(silence_ms=0.0, threshold_ms=900.0, utterance_duration_ms=MAX_TURN_MS)
    assert should_endpoint(state) is EndpointDecision.END


def test_just_under_max_turn_length_does_not_force_end() -> None:
    state = _state(silence_ms=0.0, threshold_ms=900.0, utterance_duration_ms=MAX_TURN_MS - 1)
    assert should_endpoint(state) is EndpointDecision.CONTINUE


# ── Row: "Semantic model unreachable -> timeout ends the turn" ─────────────────────────────
@pytest.mark.asyncio
async def test_semantic_check_timeout_ends_turn() -> None:
    state = _state(
        silence_ms=600.0,
        threshold_ms=500.0,
        extensions_used=MAX_EXTENSIONS_PER_UTTERANCE,
        transcript_tail="and",
    )

    async def _slow_checker(_tail: str) -> bool:
        await asyncio.sleep(1.0)
        return True

    result = await resolve_endpoint(state, semantic_checker=_slow_checker, timeout_ms=10)
    assert result is EndpointDecision.END


@pytest.mark.asyncio
async def test_semantic_check_says_complete_ends_turn() -> None:
    state = _state(
        silence_ms=600.0,
        threshold_ms=500.0,
        extensions_used=MAX_EXTENSIONS_PER_UTTERANCE,
        transcript_tail="and",
    )

    async def _checker(_tail: str) -> bool:
        return True

    assert await resolve_endpoint(state, semantic_checker=_checker) is EndpointDecision.END


@pytest.mark.asyncio
async def test_semantic_check_says_incomplete_continues() -> None:
    state = _state(
        silence_ms=600.0,
        threshold_ms=500.0,
        extensions_used=MAX_EXTENSIONS_PER_UTTERANCE,
        transcript_tail="and",
    )

    async def _checker(_tail: str) -> bool:
        return False

    assert await resolve_endpoint(state, semantic_checker=_checker) is EndpointDecision.CONTINUE


@pytest.mark.asyncio
async def test_resolve_endpoint_skips_semantic_check_when_not_needed() -> None:
    state = _state(silence_ms=100.0, threshold_ms=500.0)

    async def _checker(_tail: str) -> bool:
        raise AssertionError("must not be called when should_endpoint already decided")

    assert await resolve_endpoint(state, semantic_checker=_checker) is EndpointDecision.CONTINUE


# ── Row: "Cough / door slam -> below min utterance length -> discarded, no turn" ────────────
def test_short_detection_is_noise() -> None:
    assert is_utterance_too_short(MIN_UTTERANCE_MS - 1) is True
    assert is_utterance_too_short(MIN_UTTERANCE_MS) is False
    assert is_utterance_too_short(MIN_UTTERANCE_MS + 1) is False


def test_exceeds_max_turn_length_boundary() -> None:
    assert exceeds_max_turn_length(MAX_TURN_MS) is True
    assert exceeds_max_turn_length(MAX_TURN_MS - 1) is False


# ── Adaptive threshold tracker (Task 1.3b step 2) ───────────────────────────────────────────
def test_adaptive_threshold_falls_back_to_base_before_three_utterances() -> None:
    tracker = AdaptiveThresholdTracker()
    tracker.record_utterance([600.0])
    tracker.record_utterance([650.0])
    assert tracker.current_threshold_ms() == tracker.base_ms


def test_adaptive_threshold_uses_p90_after_three_utterances() -> None:
    tracker = AdaptiveThresholdTracker()
    for pauses in ([400.0], [420.0], [450.0]):
        tracker.record_utterance(pauses)
    threshold = tracker.current_threshold_ms()
    assert tracker.min_ms <= threshold <= tracker.max_ms
    # p90 of [400, 420, 450] via linear-interpolation rank: 420 + 0.8*(450-420) = 444.0
    assert threshold == pytest.approx(444.0, abs=0.01)


def test_adaptive_threshold_clamps_to_max() -> None:
    tracker = AdaptiveThresholdTracker()
    for _ in range(3):
        tracker.record_utterance([5000.0, 6000.0])
    assert tracker.current_threshold_ms() == tracker.max_ms


def test_adaptive_threshold_clamps_to_min() -> None:
    tracker = AdaptiveThresholdTracker()
    for _ in range(3):
        tracker.record_utterance([10.0, 20.0])
    assert tracker.current_threshold_ms() == tracker.min_ms
