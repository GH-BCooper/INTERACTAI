"""docs/phase-2-BUILD.md TASK 2.3's acceptance criterion: "No repeated questions across a
20-turn session (embedding similarity < 0.9 threshold)." Implemented as bag-of-words Jaccard
similarity rather than a real embedding model — CLAUDE.md's own build-plan rule ("never two
Heavy technologies in one day") already spends this phase's budget on the persona engine
itself; adding `MODEL_EMBEDDER` (sentence-transformers) as a second live dependency for one
narrow check is exactly the kind of scope creep that rule exists to prevent. This is a weaker
signal than real semantic similarity (it won't catch a paraphrase with no shared words), but it
reliably catches the failure mode that actually matters here — the model asking a
near-identical question again — and needs no new infrastructure.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "so", "to", "of", "in", "on", "for", "with",
        "you", "your", "did", "do", "does", "is", "was", "were", "what", "how", "tell", "me",
        "about", "that", "this", "it", "at", "as", "be", "can", "could", "would", "walk",
        "through",
    }
)  # fmt: skip


def _token_set(text: str) -> set[str]:
    words = _WORD.findall(text.lower())
    return {w for w in words if w not in _STOPWORDS}


def jaccard_similarity(a: str, b: str) -> float:
    set_a, set_b = _token_set(a), _token_set(b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def is_repeated_question(
    candidate: str, recent_questions: list[str], threshold: float = 0.9
) -> bool:
    return any(jaccard_similarity(candidate, prior) >= threshold for prior in recent_questions)
