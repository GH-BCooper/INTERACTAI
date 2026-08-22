"""docs/phase-2-BUILD.md TASK 2.5g: the narrative report. Given already-fixed scores and
verified evidence, and explicitly forbidden from contradicting them (CLAUDE.md §1.4: "Scores
come from the scorer model; prose comes from the narrator... Never let a generative model
produce a number that reaches the UI" — the narrator may *describe* a number it was given, but
never invent one).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import litellm
from pydantic import BaseModel

from ..core.config import get_settings
from ..core.logging import get_logger
from ..cost import CallStats, extract_call_stats
from ..prompts import CONTENT_PROMPTS_DIR, load_prompt
from .checks import find_contradicting_numbers, find_generic_encouragement

logger = get_logger(__name__)

_PROMPT_PATH = CONTENT_PROMPTS_DIR / "coach" / "narrator.v1.md"
PROMPT_VERSION, PROMPT_TEXT = load_prompt(_PROMPT_PATH)

MAX_ATTEMPTS = 2  # Task 2.5g: "regenerate once if triggered"


class NextActionOut(BaseModel):
    text: str
    turn_id: str | None = None


class NarrativeOutput(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]
    next_actions: list[NextActionOut]


@dataclass(frozen=True, slots=True)
class CriterionForNarrative:
    key: str
    name: str
    score: float | None  # None -> "not enough signal"
    evidence_quotes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NarrativeResult:
    summary: str
    strengths: list[str]
    growth_areas: list[str]
    next_actions: list[dict[str, object]]
    model_version: str | None  # None means the templated fallback was used, not a model


def _format_criteria_block(criteria: list[CriterionForNarrative]) -> str:
    lines = []
    for c in criteria:
        if c.score is None:
            lines.append(f"- {c.name} ({c.key}): not enough signal")
        else:
            quotes = "; ".join(f'"{q}"' for q in c.evidence_quotes[:3])
            lines.append(f"- {c.name} ({c.key}): {c.score}/5 — evidence: {quotes or '(none)'}")
    return "\n".join(lines)


def _build_messages(
    *,
    scenario_title: str,
    rubric_name: str,
    criteria: list[CriterionForNarrative],
    highlight_turn_id: str | None,
    highlight_text: str | None,
    lowlight_turn_id: str | None,
    lowlight_text: str | None,
    low_sample_size: bool,
) -> list[dict[str, str]]:
    parts = [
        f"Scenario: {scenario_title}",
        f"Rubric: {rubric_name}",
        "Scores:",
        _format_criteria_block(criteria),
    ]
    if highlight_text:
        parts.append(f'Highlight turn (turn_id={highlight_turn_id}): "{highlight_text}"')
    if lowlight_text:
        parts.append(f'Lowlight turn (turn_id={lowlight_turn_id}): "{lowlight_text}"')
    if low_sample_size:
        parts.append(
            "Note: this session had very few scoreable turns. Say so plainly in the summary."
        )
    return [
        {"role": "system", "content": PROMPT_TEXT},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _valid_turn_ids(
    highlight_turn_id: str | None, lowlight_turn_id: str | None
) -> set[str]:
    return {t for t in (highlight_turn_id, lowlight_turn_id) if t is not None}


def _template_fallback(
    criteria: list[CriterionForNarrative], *, low_sample_size: bool
) -> NarrativeResult:
    """Task 2.5's edge case: "Narrative model unavailable -> Ship the scores with a templated
    summary; report is still useful." No LLM, no blocklist/contradiction risk by construction —
    it only ever states scores it was literally handed."""
    scored = [c for c in criteria if c.score is not None]
    sample_note = " This session had very few scoreable turns." if low_sample_size else ""
    if not scored:
        summary = (
            "Not enough turns were scored with sufficient confidence to summarize this "
            "session." + sample_note
        )
        return NarrativeResult(
            summary=summary, strengths=[], growth_areas=[], next_actions=[], model_version=None
        )
    ranked = sorted(scored, key=lambda c: c.score or 0, reverse=True)
    top = ranked[: min(3, len(ranked))]
    bottom = ranked[-min(3, len(ranked)) :]
    summary = (
        f"This session scored {len(scored)} of {len(criteria)} criteria with enough signal to "
        f"report. The highest-scoring area was {top[0].name} ({top[0].score}/5); the area with "
        f"the most room to grow was {bottom[0].name} ({bottom[0].score}/5)." + sample_note
    )
    strengths = [f"{c.name} scored {c.score}/5." for c in top]
    growth_areas = [
        f"{c.name} scored {c.score}/5 — the most room to improve here." for c in bottom
    ]
    return NarrativeResult(
        summary=summary,
        strengths=strengths,
        growth_areas=growth_areas,
        next_actions=[],
        model_version=None,
    )


async def generate_narrative(
    *,
    model: str | None = None,
    scenario_title: str,
    rubric_name: str,
    criteria: list[CriterionForNarrative],
    highlight_turn_id: str | None = None,
    highlight_text: str | None = None,
    lowlight_turn_id: str | None = None,
    lowlight_text: str | None = None,
    low_sample_size: bool = False,
) -> tuple[NarrativeResult, CallStats | None]:
    settings = get_settings()
    model = model or settings.model_narrator
    valid_scores = {c.score for c in criteria if c.score is not None}
    allowed_turn_ids = _valid_turn_ids(highlight_turn_id, lowlight_turn_id)

    messages = _build_messages(
        scenario_title=scenario_title,
        rubric_name=rubric_name,
        criteria=criteria,
        highlight_turn_id=highlight_turn_id,
        highlight_text=highlight_text,
        lowlight_turn_id=lowlight_turn_id,
        lowlight_text=lowlight_text,
        low_sample_size=low_sample_size,
    )

    for attempt in range(MAX_ATTEMPTS):
        t0 = time.perf_counter()
        elapsed_ms = 0.0
        try:
            response = await litellm.acompletion(
                model=model, messages=messages, response_format=NarrativeOutput
            )
            parsed = NarrativeOutput.model_validate_json(response.choices[0].message.content)
        except Exception:
            logger.warning("narrator_call_failed", model=model, attempt=attempt)
            continue
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.debug("narrator_call", model=model, attempt=attempt, elapsed_ms=elapsed_ms)

        blob = " ".join([parsed.summary, *parsed.strengths, *parsed.improvements])
        encouragement_hits = find_generic_encouragement(blob)
        contradictions = find_contradicting_numbers(blob, valid_scores)
        if encouragement_hits or contradictions:
            logger.info(
                "narrator_post_check_failed",
                attempt=attempt,
                encouragement_hits=encouragement_hits,
                contradictions=contradictions,
            )
            continue

        next_actions: list[dict[str, object]] = [
            {
                "text": a.text,
                "turn_id": a.turn_id if a.turn_id in allowed_turn_ids else None,
            }
            for a in parsed.next_actions
        ]
        result = NarrativeResult(
            summary=parsed.summary,
            strengths=parsed.strengths,
            growth_areas=parsed.improvements,
            next_actions=next_actions,
            model_version=f"narrator:{model}:{PROMPT_VERSION}",
        )
        return result, extract_call_stats(response, total_latency_ms=elapsed_ms)

    logger.warning("narrator_fallback_to_template", model=model)
    return _template_fallback(criteria, low_sample_size=low_sample_size), None
