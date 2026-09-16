"""docs/phase-5-BUILD.md TASK 5.2b — synthetic generation. Fills "the tails of the distribution,
which real data never provides": most real answers are mediocre, almost none are terrible or
excellent, so a model that never sees a 1 or a 5 can't predict one.

Real LLM calls (litellm, same call pattern as services/coach/app/scorer/prompted.py), tagged
`source="synthetic"` everywhere downstream — never conflated with real speech. Two hard rules
from the spec this module exists to honour and that split.py (already tested) separately
enforces on the output: **the instructed level is a generation parameter, not a label** (a
synthetic turn is not scored until a human annotates it, same as any other turn), and generated
answers must vary in "phrasing, length and filler density so the model does not learn 'the
synthetic style' as a shortcut feature" — the prompt below asks for that explicitly and the
per-call temperature is not pinned to 0.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from uuid import uuid4

import litellm
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # services/training on sys.path
from config import get_training_settings  # noqa: E402

QUALITY_LEVEL_INSTRUCTIONS = {
    1: (
        "a nervous candidate who gives no concrete detail, hedges constantly, and barely "
        "answers the question asked"
    ),
    2: (
        "a candidate who eventually gets to a relevant point but pads the answer with "
        "repetition and stays mostly abstract"
    ),
    3: (
        "an average candidate who answers the question adequately, with a couple of concrete "
        "details but an unclear structure"
    ),
    4: (
        "a solid candidate who structures the answer clearly with mostly specific detail and "
        "only minor hedging"
    ),
    5: (
        "a strong candidate with a clear arc (situation, action, outcome), specific numbers or "
        "named tools, and confident, concise delivery"
    ),
}

FILLER_DENSITY_HINTS = (
    "with no filler words at all",
    "with an occasional 'um' or 'you know'",
    "with frequent filler words and false starts, the way real spontaneous speech sounds",
)


class SyntheticTurn(BaseModel):
    question: str
    answer: str


_PROMPT = """You are generating a synthetic training example for an interview-coaching product's \
answer-quality model. You will invent a plausible interview question for the given scenario, \
then write an answer to it as {persona_description}, {filler_hint}.

Scenario family: {family}
Scenario difficulty: {difficulty}
Scenario brief: {brief}

Vary sentence length and phrasing naturally — do not produce a generic, templated-sounding \
answer. The answer should read like a transcript of real spoken speech (informal grammar, \
occasional restarts), not polished prose. Return between 40 and 220 words for the answer.

This is synthetic training data, not a real conversation — there is no real candidate and no \
real interviewer. Do not mention that it is synthetic anywhere in the question or answer text \
themselves."""


async def generate_one(
    *, family: str, difficulty: str, brief: str, quality_level: int, model: str | None = None
) -> SyntheticTurn:
    settings = get_training_settings()
    persona_description = QUALITY_LEVEL_INSTRUCTIONS[quality_level]
    filler_hint = random.choice(FILLER_DENSITY_HINTS)  # noqa: S311 - not security-sensitive
    prompt = _PROMPT.format(
        persona_description=persona_description,
        filler_hint=filler_hint,
        family=family,
        difficulty=difficulty,
        brief=brief,
    )
    response = await litellm.acompletion(
        model=model or settings.training_generator_model,
        messages=[{"role": "user", "content": prompt}],
        response_format=SyntheticTurn,
        temperature=0.9,
    )
    content = response.choices[0].message.content
    return SyntheticTurn.model_validate_json(content)


async def generate_batch(
    scenarios: list[dict[str, str]],
    *,
    per_scenario_per_level: int = 1,
    levels: tuple[int, ...] = (1, 2, 3, 4, 5),
    model: str | None = None,
) -> list[dict[str, object]]:
    """Returns plain dicts (not DB rows) — `write_synthetic_turns` below is the only place that
    touches Postgres, so this function is testable (with a monkeypatched `generate_one`) without
    a database, matching this module's sibling `split.py`'s no-I/O design as far as generation
    logic itself is concerned.
    """
    out: list[dict[str, object]] = []
    batch_id = uuid4().hex[:12]
    for scenario in scenarios:
        for level in levels:
            for _ in range(per_scenario_per_level):
                turn = await generate_one(
                    family=scenario["family"],
                    difficulty=scenario["difficulty"],
                    brief=scenario["brief"],
                    quality_level=level,
                    model=model,
                )
                unique_suffix = uuid4().hex[:8]
                speaker_key = f"synthetic:{batch_id}:{scenario['id']}:{level}:{unique_suffix}"
                out.append(
                    {
                        "scenario_id": scenario["id"],
                        "quality_level": level,
                        "question": turn.question,
                        "answer": turn.answer,
                        "speaker_key": speaker_key,
                    }
                )
    return out
