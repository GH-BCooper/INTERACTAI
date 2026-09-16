"""Phase 6 TASK 6.3 — the pure parts of the Level 1 / Level 2 suites. The gates are tested here
directly ("RTF > 1.0 fails the suite rather than warning", "difficulty separation is statistically
asserted"); the model-backed parts are exercised by `make eval-speech` / `make eval-persona`."""

from __future__ import annotations

import pytest

from scripts.eval_common import normalize_words, percentile, word_error_rate
from scripts.eval_persona import (
    acknowledgement_words,
    last_question,
    mann_whitney_greater,
    separation_verdict,
    verify_quote,
)
from scripts.eval_speech import rtf_gate


def test_wer_counts_substitutions_insertions_deletions() -> None:
    assert word_error_rate("the cat sat", "the cat sat") == 0.0
    assert word_error_rate("the cat sat", "the dog sat") == pytest.approx(1 / 3)
    assert word_error_rate("the cat sat", "the cat") == pytest.approx(1 / 3)
    assert word_error_rate("the cat", "the big cat") == pytest.approx(1 / 2)


def test_wer_ignores_case_punctuation_and_spelled_numbers() -> None:
    assert normalize_words("Ten minutes, OK?") == ["10", "minutes", "ok"]
    assert word_error_rate("about ten minutes ago.", "About 10 minutes ago") == 0.0


def test_rtf_above_one_fails_not_warns() -> None:
    assert rtf_gate("ASR", 0.42) is None
    assert rtf_gate("ASR", 1.0) is None
    failure = rtf_gate("Synthesis", 1.01)
    assert failure is not None and "design fails" in failure


def test_percentile_interpolates() -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([], 95) is None


def test_acknowledgement_is_words_before_first_question() -> None:
    assert acknowledgement_words("Okay. What happened next?") == 1
    assert acknowledgement_words("Thanks, that is really helpful context. Who decided?") == 6
    assert acknowledgement_words("Who decided?") == 0
    assert last_question("Got it. Why? And who approved it?") == "And who approved it?"


def test_judge_quote_must_be_verbatim() -> None:
    reply = "Great answer! What did you measure?"
    assert verify_quote(reply, "Great answer!")
    assert not verify_quote(reply, "great answer")  # not an exact substring
    assert not verify_quote(reply, None)


def test_separation_passes_only_when_every_measure_separates() -> None:
    separated = {
        "gentle": {
            "followup_rate": [0, 0, 0.1, 0, 0, 0],
            "ack_words": [12, 14, 11, 13, 15, 12],
            "interruptions": [0] * 6,
        },
        "standard": {"followup_rate": [0.5] * 6, "ack_words": [5] * 6, "interruptions": [0] * 6},
        "hard": {
            "followup_rate": [1, 0.9, 1, 1, 0.8, 1],
            "ack_words": [1, 0, 2, 1, 0, 1],
            "interruptions": [1, 1, 2, 1, 1, 1],
        },
    }
    assert separation_verdict(separated)["passed"] is True

    decorative = {tier: dict(separated["gentle"]) for tier in ("gentle", "standard", "hard")}
    verdict = separation_verdict(decorative)
    assert verdict["passed"] is False
    assert verdict["separated"] == {
        "followup_rate": False,
        "ack_words": False,
        "interruptions": False,
    }


def test_identical_constant_samples_are_not_separable() -> None:
    assert mann_whitney_greater([0, 0, 0], [0, 0, 0]) == 1.0
    assert mann_whitney_greater([3, 4, 5, 6, 7, 8], [0, 1, 0, 1, 0, 1]) < 0.05
