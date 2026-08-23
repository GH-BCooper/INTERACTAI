"""Task 4.5b (AS-06): "PII scrubbing... runs before any transcript reaches an annotation
interface, including your own." Wired into generate_report (services/coach/app/report/build.py)
so `turns.text_scrubbed` is populated once, session-wide, whenever a report is generated —
alongside the unscrubbed `turns.text` every existing report/replay/evidence-span surface keeps
reading unchanged (CLAUDE.md §1.5's exact-substring evidence verification depends on the
original, untouched text).

HONEST LIMITATION (documented per Task 4.5b's own instruction, not glossed over): automated
NER-based scrubbing on conversational, spoken-then-transcribed text is imperfect. spaCy's
`en_core_web_sm` model:
  - misses unusual or non-Western names it wasn't trained to recognise as PERSON entities
  - can mistake a company name that is also a common noun (e.g. "Amazon", "Anchor") for
    ordinary text, or conversely flag an ordinary word as an entity
  - does not perform coreference resolution: "John Smith" and a later bare "John" referring to
    the same person are NOT guaranteed to receive the same pseudonym, since each is only
    recognised as an entity in its own right, not linked to the other
A manual review pass over any set of transcripts destined for actual human annotation or
training-data use is required before this scrubbed text should be treated as fully de-identified
— this module reduces exposure, it does not guarantee it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import spacy

# PERSON/ORG/GPE per Task 4.5b's own list ("PERSON, ORG, GPE"). GPE (geo-political entity —
# spaCy's label for countries/cities/states) is surfaced to callers as "LOCATION", the more
# readable term the pseudonym itself uses.
_ENTITY_LABEL_TO_PSEUDONYM_LABEL = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "LOCATION"}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}(?:\.[A-Za-z]{2,})?")
# A run of 7+ digits with optional separators, not immediately adjacent to more digits — catches
# "555-123-4567", "(555) 123 4567", "+1 555 123 4567" without also matching a bare long number
# that isn't actually phone-shaped (a salary regex below has its own, separate rule for those).
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\-.\s()]{6,}\d)(?!\d)")
# "$120,000", "$120k", "150000 dollars", "140k a year", "130,000 USD" — deliberately broad; a
# false positive here (scrubbing a number that wasn't actually a salary) is a much smaller harm
# than a false negative on an actual figure a candidate stated out loud.
_SALARY_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?[kK]\b)?"
    r"|\b\d[\d,]{1,}(?:\.\d+)?(?:\s?[kK]\b)?\s?"
    r"(?:dollars|usd|per year|/\s?year|/\s?yr|a year|annually)\b"
    # A bare "165k"/"85K" with no surrounding keyword at all — common shorthand for a salary
    # figure in an interview transcript specifically. Bounded to 2-3 digits so it doesn't reach
    # for an unrelated "1948k" or similar; false positives here (e.g. "we had 500k users") are a
    # smaller harm than missing an actual figure someone stated (module docstring).
    r"|\b\d{2,3}[kK]\b",
    re.IGNORECASE,
)

_SPACY_MODEL_NAME = "en_core_web_sm"


@lru_cache
def _nlp() -> spacy.language.Language:  # pragma: no cover — trivial, exercised via scrub_text
    return spacy.load(_SPACY_MODEL_NAME)


@dataclass
class PseudonymTracker:
    """Task 4.5b: "Replaces with stable pseudonyms within a session ([PERSON_1] refers to the
    same person throughout)." One tracker per session — never shared across sessions, so the
    same real name in two different users' transcripts doesn't collide on the same pseudonym
    number by coincidence."""

    _counters: dict[str, int] = field(default_factory=dict)
    _assigned: dict[tuple[str, str], str] = field(default_factory=dict)

    def pseudonym_for(self, label: str, original_text: str) -> str:
        key = (label, original_text.strip().lower())
        if key not in self._assigned:
            self._counters[label] = self._counters.get(label, 0) + 1
            self._assigned[key] = f"[{label}_{self._counters[label]}]"
        return self._assigned[key]


@dataclass(frozen=True, slots=True)
class _Span:
    start: int
    end: int
    replacement: str


def _entity_spans(text: str, tracker: PseudonymTracker) -> list[_Span]:
    doc = _nlp()(text)
    spans = []
    for ent in doc.ents:
        label = _ENTITY_LABEL_TO_PSEUDONYM_LABEL.get(ent.label_)
        if label is None:
            continue
        spans.append(_Span(ent.start_char, ent.end_char, tracker.pseudonym_for(label, ent.text)))
    return spans


def _regex_spans(text: str, tracker: PseudonymTracker) -> list[_Span]:
    spans = []
    for pattern, label in ((_EMAIL_RE, "EMAIL"), (_PHONE_RE, "PHONE"), (_SALARY_RE, "SALARY")):
        for match in pattern.finditer(text):
            spans.append(
                _Span(match.start(), match.end(), tracker.pseudonym_for(label, match.group()))
            )
    return spans


def _resolve_overlaps(spans: list[_Span]) -> list[_Span]:
    """Greedy interval scheduling: sort by start (longest match first as a tiebreaker so a
    multi-word entity like "New York City" wins over a shorter overlapping regex match), then
    keep each span only if it doesn't overlap one already kept."""
    ordered = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    resolved: list[_Span] = []
    last_end = -1
    for span in ordered:
        if span.start < last_end:
            continue
        resolved.append(span)
        last_end = span.end
    return resolved


def scrub_text(text: str, tracker: PseudonymTracker) -> str:
    """Pure function: given a tracker (carrying whatever pseudonyms have already been assigned
    elsewhere in the same session), returns `text` with every detected PERSON/ORG/GPE entity,
    email, phone number and salary figure replaced by a stable pseudonym."""
    if not text.strip():
        return text
    spans = _resolve_overlaps(_entity_spans(text, tracker) + _regex_spans(text, tracker))
    if not spans:
        return text

    pieces: list[str] = []
    cursor = 0
    for span in spans:
        pieces.append(text[cursor : span.start])
        pieces.append(span.replacement)
        cursor = span.end
    pieces.append(text[cursor:])
    return "".join(pieces)


def scrub_session_turns(turns: list[dict[str, object]]) -> dict[str, str]:
    """One tracker shared across every turn in a session, so pseudonyms stay stable session-wide
    (Task 4.5b) rather than resetting per turn. `turns` is a list of row-mapping dicts shaped
    like services/coach/app/db/repository.py::get_turns_for_session's return value (real values,
    not all strings — e.g. `id` is a UUID); only `id` and `text` are read here. Returns turn id
    (stringified) -> scrubbed text, ready for a bulk `text_scrubbed` write."""
    tracker = PseudonymTracker()
    return {str(t["id"]): scrub_text(str(t["text"]), tracker) for t in turns}
