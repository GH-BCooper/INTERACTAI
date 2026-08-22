"""Task 1.4 acceptance: "Delivery metrics match hand-computed values on a committed fixture,
exactly." The fixture is the word-timing list below; the expected values are computed by hand
in each test's comment.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.realtime.app.asr.delivery_metrics import compute_delivery_metrics


@dataclass
class W:
    word: str
    start_ms: int
    end_ms: int


def test_hand_computed_fixture_exact() -> None:
    # "So, um, I built the pipeline last quarter" — 8 words, one filler ("um"), one 400ms pause
    # after it (thinking), utterance spans 0..4000ms.
    words = [
        W("So", 0, 200),
        W("um", 300, 500),  # standalone filler
        W("I", 900, 1000),  # 400ms pause before this word (900-500)
        W("built", 1000, 1300),
        W("the", 1300, 1400),
        W("pipeline", 1400, 1900),
        W("last", 1900, 2100),
        W("quarter", 2100, 2500),
    ]
    metrics = compute_delivery_metrics(words, utterance_start_ms=0, utterance_end_ms=4000)

    assert metrics.word_count == 8
    assert metrics.filler_count == 1
    assert metrics.filler_rate == 1 / 8
    # wpm = 8 words / (4000ms / 60000) = 8 / (0.06666...) = 120.0
    assert metrics.wpm == 120.0
    # longest pause: 400ms gap before "I" (900-500) vs trailing gap 4000-2500=1500ms -> max=1500
    assert metrics.longest_pause_ms == 1500
    # speech_ms = sum of (end-start): 200+200+100+300+100+500+200+400 = 2000
    assert metrics.speech_ratio == 2000 / 4000


def test_multi_word_filler_counted_once() -> None:
    words = [W("you", 0, 100), W("know", 100, 200), W("it", 200, 300), W("worked", 300, 500)]
    metrics = compute_delivery_metrics(words, utterance_start_ms=0, utterance_end_ms=500)
    assert metrics.filler_count == 1  # "you know" -> one filler, not zero, not two


def test_standalone_token_does_not_over_count_substrings() -> None:
    # "unlike" and "liked" must not be counted as the filler "like" via substring matching.
    words = [
        W("It's", 0, 100),
        W("unlike", 100, 300),
        W("anything", 300, 600),
        W("I've", 600, 700),
        W("liked", 700, 900),
    ]
    metrics = compute_delivery_metrics(words, utterance_start_ms=0, utterance_end_ms=900)
    assert metrics.filler_count == 0


def test_empty_utterance_has_zero_metrics_no_division_error() -> None:
    metrics = compute_delivery_metrics([], utterance_start_ms=0, utterance_end_ms=1000)
    assert metrics.word_count == 0
    assert metrics.filler_count == 0
    assert metrics.filler_rate == 0.0
    assert metrics.wpm == 0.0
    assert metrics.speech_ratio == 0.0


def test_speech_ratio_never_exceeds_one() -> None:
    # pathological/overlapping timings shouldn't be able to push the ratio above 1.0
    words = [W("a", 0, 500), W("b", 400, 900)]
    metrics = compute_delivery_metrics(words, utterance_start_ms=0, utterance_end_ms=500)
    assert metrics.speech_ratio <= 1.0
