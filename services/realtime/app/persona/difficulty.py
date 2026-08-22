"""docs/phase-2-BUILD.md TASK 2.3c: difficulty as parameters, not three prompts. Parsed from
`sessions.brief["difficulty_params"]` — the single active tier's dict, already resolved at
session-creation time by `services/api/app/services/session_service.py::_compile_brief`
(the frozen brief carries only the tier that's actually in play, not the full gentle/standard/
hard lookup table — that full table lives on `scenarios.difficulty_params` instead).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AckLength = Literal["long", "short", "minimal"]


@dataclass(frozen=True, slots=True)
class DifficultyParams:
    followups_on_vague: int  # gentle 0 / standard 1 / hard 3
    hint_after_pause_ms: int | None  # 4000 / None / None
    interrupt_over_words: int | None  # None / None / 120
    ack_length: AckLength
    silence_after_answer_ms: int  # 0 / 0 / 1500
    challenge_claims: bool = False
    time_pressure: bool = False


def parse_difficulty_params(raw: dict[str, Any]) -> DifficultyParams:
    """Content-authoring convention (content/scenarios/*.yaml): a tier only states fields that
    differ from the default — `challenge_claims`/`time_pressure` are absent (implicitly False)
    on `gentle`/`standard`, present and `true` only on `hard`. Missing `ack_length` would be an
    authoring bug, not a legitimate default, so it's the one field with no `.get()` fallback."""
    return DifficultyParams(
        followups_on_vague=int(raw.get("followups_on_vague", 0)),
        hint_after_pause_ms=raw.get("hint_after_pause_ms"),
        interrupt_over_words=raw.get("interrupt_over_words"),
        ack_length=raw["ack_length"],
        silence_after_answer_ms=int(raw.get("silence_after_answer_ms", 0)),
        challenge_claims=bool(raw.get("challenge_claims", False)),
        time_pressure=bool(raw.get("time_pressure", False)),
    )


def render_difficulty_instructions(params: DifficultyParams) -> str:
    """Task 2.3c: "rendered into the semi-static layer as explicit behavioural instructions."
    Plain imperative sentences, matching the static layer's style — a model follows "ask one
    follow-up on a vague answer" far more reliably than a bare `followups_on_vague: 1`."""
    lines: list[str] = []
    if params.followups_on_vague <= 0:
        lines.append(
            "If an answer is vague, accept it and move on rather than pressing for more detail."
        )
    else:
        plural = "s" if params.followups_on_vague != 1 else ""
        lines.append(
            f"If an answer is vague, follow up to press for specifics — up to "
            f"{params.followups_on_vague} follow-up{plural} on the same point before moving on."
        )
    if params.hint_after_pause_ms is not None:
        lines.append(
            "If the candidate goes silent for a while, offer a small hint or rephrase the "
            "question rather than waiting them out."
        )
    else:
        lines.append("Do not offer hints during a pause — let the candidate work through it.")
    if params.interrupt_over_words is not None:
        lines.append(
            f"If the candidate rambles past roughly {params.interrupt_over_words} words without "
            f"getting to the point, interrupt and redirect them — politely but without waiting "
            f"for a natural pause."
        )
    ack_instruction = {
        "long": "Acknowledge answers warmly and at some length before moving on.",
        "short": "Acknowledge answers briefly — a few words — before moving on.",
        "minimal": "Acknowledge answers minimally or not at all before moving on.",
    }[params.ack_length]
    lines.append(ack_instruction)
    if params.silence_after_answer_ms >= 1000:
        lines.append(
            "Leave a deliberate pause after the candidate finishes answering before you speak "
            "again — do not rush to fill silence."
        )
    if params.challenge_claims:
        lines.append(
            "Challenge claims that sound unverified or convenient — ask how they know, who "
            "would confirm it, or what the actual number was."
        )
    if params.time_pressure:
        lines.append(
            "Behave as though time is short — mention the clock if the candidate rambles, and "
            "keep the pace brisk."
        )
    return "\n".join(f"- {line}" for line in lines)
