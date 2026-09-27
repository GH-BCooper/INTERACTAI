"""docs/phase-2-BUILD.md TASK 2.3e/2.6: the post-generation check. "If the reply contains any
rubric criterion name, any system-prompt fragment, or a coaching phrase from a blocklist,
discard and regenerate once with a reinforced instruction. If it fails twice, use a canned
in-character deflection."

Pure functions — no model, no IO — so the safety suite (Task 2.6, CI-enforced) can assert
against them directly without a live model call for every case.
"""

from __future__ import annotations

import re

# Every criterion key/name across both seeded rubrics (content/rubrics/*.yaml). Hardcoded
# rather than fetched per-session: this is a static safety net that must never depend on a DB
# round trip landing on the persona's hot generation path, and the rubric set changes rarely
# enough that a new criterion is a code change anyway (CLAUDE.md §11: prompts/rubrics are
# versioned content — adding one is deliberate, not implicit).
RUBRIC_CRITERION_TERMS = (
    "structure",
    "specificity",
    "relevance",
    "concision",
    "confidence",
    "technical_depth",
    "technical depth",
    "tradeoff_reasoning",
    "tradeoff reasoning",
    "anchoring",
    "justification",
    "concession_discipline",
    "concession discipline",
)

COACHING_BLOCKLIST = (
    "rubric",
    "criteria",
    "criterion",
    "score you",
    "scoring you",
    "you scored",
    "your score",
    "evaluate you",
    "evaluating you",
    "grade you",
    "grading you",
    "as an interviewer i would rate",
    "on a scale of",
    "out of 5",
    "out of five",
    "next time try",
    "for feedback",
    "tip for next time",
)

# Level 2 (Task 6.3b) found the real hole in the list above: every character break the persona
# judge caught in the 2026-09-16 run was *praise* ("Sure, that's impressive. Can you tell me more
# about…"), which is evaluative feedback on answer quality and so a break by the judge's own
# definition (content/prompts/eval/persona-judge.v1.md), but contains no coaching or grading
# phrase. Praise is matched as whole phrases, never bare adjectives, because the persona has
# legitimate reasons to say "impressive" ("what's the most impressive system you've built?") or
# "perfect" ("in a perfect world…") inside an ordinary question. The judge explicitly rules that
# neutral acknowledgements ("Okay.", "Thanks.", "Got it.", "I see.") are NOT breaks, and the
# difficulty ladder depends on acknowledgements existing at all (`ack_length`), so nothing here
# may match a bare acknowledgement.
PRAISE_BLOCKLIST = (
    # evaluative verdicts on the answer/example itself
    "good answer",
    "great answer",
    "strong answer",
    "excellent answer",
    "solid answer",
    "nice answer",
    "perfect answer",
    "compelling answer",
    "good example",
    "great example",
    "strong example",
    "excellent example",
    "perfect example",
    "good point",
    "great point",
    "excellent point",
    # evaluative verdicts phrased as a reaction
    "that's impressive",
    "that is impressive",
    "very impressive",
    "quite impressive",
    "pretty impressive",
    "impressive work",
    "i'm impressed",
    "i am impressed",
    "that's great",
    "that is great",
    "that's excellent",
    "that is excellent",
    "that's fantastic",
    "that's wonderful",
    "that's brilliant",
    "that's terrific",
    "that's perfect",
    "that's exactly right",
    "exactly what i was looking for",
    "that was great",
    "that was excellent",
    "that was a strong",
    "that was really good",
    "that's really good",
    "that's very good",
    "spot on",
    "nailed it",
    "you nailed",
    "i like that",
    "i love that",
    # "that sounds <positive>" — both of these are real replies from the 2026-09-27 Level 2 run
    # that the list above missed. Only positive completions are listed: "that sounds like a lot of
    # work" is an ordinary neutral observation and must keep passing.
    "that sounds reasonable",
    "that sounds good",
    "that sounds solid",
    "that sounds sensible",
    "that sounds right",
    "that sounds smart",
    "that sounds strong",
    "that sounds impressive",
    "sounds like a significant improvement",
    "sounds like a big improvement",
    "that's a significant improvement",
    # evaluative verdicts on the candidate
    "well done",
    "nicely done",
    "well put",
    "nicely put",
    "well explained",
    "explained that clearly",
    "explained that well",
    "good job",
    "great job",
    "nice job",
    "good work",
    "great work",
    "you did well",
    "you handled that well",
    # Not bare "strong candidate": "what made it a strong candidate for caching?" is ordinary
    # technical English and a false positive here costs a regeneration on the latency path.
    "you're a strong candidate",
    "you are a strong candidate",
)

_QUESTION_MARK = re.compile(r"\?")


def contains_rubric_leak(text: str) -> list[str]:
    lowered = text.lower()
    return [term for term in RUBRIC_CRITERION_TERMS if term in lowered]


def contains_coaching_phrase(text: str) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in COACHING_BLOCKLIST if phrase in lowered]


def contains_praise(text: str) -> list[str]:
    """Separate from `contains_coaching_phrase` so a violation reason says which rule fired —
    the Level 2 report distinguishes praise from coaching and grading, and so should the log."""
    lowered = text.lower()
    return [phrase for phrase in PRAISE_BLOCKLIST if phrase in lowered]


def contains_system_prompt_fragment(text: str, static_prompt_text: str) -> bool:
    """A crude but effective check: any run of 8+ consecutive words shared between the reply
    and the static prompt almost certainly means the model quoted its own instructions rather
    than generated a real in-character line."""
    words = re.findall(r"\w+", static_prompt_text.lower())
    if len(words) < 8:
        return False
    reply_lower = text.lower()
    window = 8
    for i in range(len(words) - window + 1):
        phrase = " ".join(words[i : i + window])
        if phrase in reply_lower:
            return True
    return False


def has_multiple_questions(text: str) -> bool:
    """Task 2.3a: "Ask one question at a time." Task 2.3's edge case: "Model asks two
    questions -> Post-check detects a second '?'; regenerate once." Counts real question marks
    only — decimals/abbreviations aren't a concern here since '?' never appears in either."""
    return len(_QUESTION_MARK.findall(text)) >= 2


def check_reply(text: str, static_prompt_text: str) -> list[str]:
    """Returns a list of violation reasons; empty means the reply passed. A single entry point
    so every caller (turn.py, the safety suite) runs exactly the same checks in the same
    order.

    A genuine distress-exit reply (`is_distress_exit_reply`) skips every check below and
    always passes. It's short, adjacent in wording to its own prompt instruction, and not
    something a user can provoke arbitrarily (only the model, following the static prompt's
    exact-marker instruction, decides to say it) — so it's exactly the kind of reply these
    heuristics (built to catch rubric leaks, coaching phrases, quoted instructions) could
    plausibly misfire on. Task 2.6/AS-07: this is the one reply that must never be discarded
    and replaced with a generic canned deflection, in a real crisis of all moments."""
    if is_distress_exit_reply(text):
        return []
    violations: list[str] = []
    if leaked := contains_rubric_leak(text):
        violations.append(f"rubric_leak:{','.join(leaked)}")
    if coaching := contains_coaching_phrase(text):
        violations.append(f"coaching_phrase:{','.join(coaching)}")
    if praise := contains_praise(text):
        violations.append(f"praise:{','.join(praise)}")
    if contains_system_prompt_fragment(text, static_prompt_text):
        violations.append("system_prompt_fragment")
    if has_multiple_questions(text):
        violations.append("multiple_questions")
    return violations


DISTRESS_EXIT_MARKER = "i'm pausing this practice session."


def is_distress_exit_reply(text: str) -> bool:
    """Task 2.6 (AS-07): the static prompt (content/prompts/persona/static.v1.md, v1.2.0)
    requires a real distress-exit reply to open with this exact sentence, word for word — a
    fixed marker rather than open-ended pattern matching on free-generated text, so detecting
    "the persona just broke character for real distress" is a reliable string check, not a
    guess. `turn.py` uses this to end the session with `end_reason="distress_exit"` and skip
    coach enqueue for it (CS-*/AS-07: no scored report for a distress exit)."""
    return text.strip().lower().startswith(DISTRESS_EXIT_MARKER)


CANNED_DEFLECTIONS = (
    "Let's stay focused on the conversation — go ahead and answer the question.",
    "I'd rather hear more from you on that. Go ahead.",
    "Let's keep going — what's your answer?",
)


def pick_canned_deflection(turn_index: int) -> str:
    """Task 2.3e: "If it fails twice, use a canned in-character deflection." Deterministic by
    turn index (not random) so a repeated failure in the same turn during tests is
    reproducible."""
    return CANNED_DEFLECTIONS[turn_index % len(CANNED_DEFLECTIONS)]
