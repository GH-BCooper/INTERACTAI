"""docs/phase-2-BUILD.md TASK 2.5g's two post-checks, as pure functions so they're testable
without a model call: the generic-encouragement blocklist and the score-contradiction check.
"""

from __future__ import annotations

import re

# Task 2.5g: "'great job', 'well done', 'keep it up' and similar" — matched as phrases, not
# single words, so legitimate uses of e.g. "well" or "job" elsewhere in a sentence don't trip it.
ENCOURAGEMENT_BLOCKLIST = (
    "great job",
    "well done",
    "keep it up",
    "nice work",
    "good job",
    "way to go",
    "you got this",
    "proud of you",
    "amazing job",
    "excellent work",
)

_SCORE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*5\b", re.IGNORECASE)


def find_generic_encouragement(text: str) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in ENCOURAGEMENT_BLOCKLIST if phrase in lowered]


def find_contradicting_numbers(text: str, valid_scores: set[float]) -> list[str]:
    """Task 2.5g: "A post-check asserts the narrative contains no number that contradicts a
    score." Finds every "`X`/5" or "`X` out of 5" in the text and flags any `X` that doesn't
    match one of the session's actual (non-gated) scores — the narrator is only ever handed
    real scores, so a number in this shape that matches none of them was either invented or
    misremembered, either of which is exactly the failure mode this check exists to catch."""
    found = _SCORE_PATTERN.findall(text)
    contradictions = []
    for raw in found:
        value = float(raw)
        if value not in valid_scores:
            contradictions.append(raw)
    return contradictions
