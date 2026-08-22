"""docs/phase-2-BUILD.md TASK 2.5d: evidence verification — NON-NEGOTIABLE. "Exact substring
match. Unverifiable spans are DISCARDED and the score is downgraded to low confidence. There is
no fuzzy fallback." CLAUDE.md §1.5 repeats this as a hard invariant.

Design note on the two-step shape (`locate_quote` then `verify_spans`): a scorer model is asked
to quote evidence verbatim (Task 2.5c), not to compute character offsets — LLMs are unreliable
at counting characters but can usually reproduce a short quote exactly. `locate_quote` turns a
claimed quote into a `Span` by finding it in the answer (the one place "whitespace normalisation
is permitted" applies — never paraphrase, never fuzzy/semantic matching); `verify_spans` is the
final gate every `Span` must pass before it's allowed into a `CriterionScore`, re-confirming the
slice it names is real and non-empty. Splitting them means a caller can't accidentally skip
verification by constructing a `Span` some other way — `verify_spans` is where every path funnels
before scores get written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import Span

_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text).strip()


def locate_quote(answer: str, quote: str) -> Span | None:
    """Finds `quote` verbatim in `answer`. Exact match first (the common case; keeps offsets
    trivial); falling back to a whitespace-insensitive search only if that fails — never a
    semantic or paraphrase match. Returns `None` if the quote does not appear at all (a
    hallucinated span, Task 2.5d's edge case), never a best-guess position."""
    if not quote:
        return None
    idx = answer.find(quote)
    if idx != -1:
        return Span(start=idx, end=idx + len(quote))

    normalized_quote = _normalize_ws(quote)
    if not normalized_quote:
        return None
    pattern = re.escape(normalized_quote).replace(r"\ ", r"\s+")
    match = re.search(pattern, answer)
    if match is None:
        return None
    return Span(start=match.start(), end=match.end())


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verified_spans: list[Span]
    all_verified: bool
    evidence_validity: float  # Task 2.5d: fraction of spans found verbatim, logged per turn


def verify_spans(answer: str, quotes: list[str]) -> VerificationResult:
    """The one function every scorer implementation's evidence must pass through. Takes the
    model's raw claimed quotes (not pre-built spans — see module docstring), locates each one,
    and structurally re-confirms every located span actually slices `answer` correctly before
    it's accepted. Never raises on a bad quote; a hallucinated or malformed one is simply
    dropped, exactly as Task 2.5d requires."""
    if not quotes:
        return VerificationResult(verified_spans=[], all_verified=True, evidence_validity=1.0)

    verified: list[Span] = []
    for quote in quotes:
        span = locate_quote(answer, quote)
        if span is None:
            continue
        if not (0 <= span.start < span.end <= len(answer)):
            continue  # structurally invalid offsets — treated the same as "not found"
        verified.append(span)

    evidence_validity = round(len(verified) / len(quotes), 4)
    return VerificationResult(
        verified_spans=verified,
        all_verified=len(verified) == len(quotes),
        evidence_validity=evidence_validity,
    )


def apply_confidence_penalty(confidence: float, verification: VerificationResult) -> float:
    """Task 2.5d: "If any span for a criterion fails, that criterion's confidence is multiplied
    by 0.5... If all spans fail, confidence is set to 0." Applied only when quotes were actually
    requested — a criterion with no evidence requirement at all (never happens in this rubric
    design, but the function shouldn't assume) is untouched."""
    if verification.all_verified:
        return confidence
    if not verification.verified_spans:
        return 0.0
    return confidence * 0.5
