"""docs/phase-2-BUILD.md TASK 2.3e: streaming and enforcement. `max_tokens` as a hard stop in
addition to the prompt rule; post-generation checks (safety.py) with one regenerate and a
canned fallback; word-cap trimming to the last complete clause.

Design choice worth stating plainly: the model's response is buffered in full here before this
module returns, rather than forwarded to the chunker/TTS pipeline token-by-token as it streams
(the way Phase 1's `persona/minimal.py` did). Task 2.3e's post-generation check has to see the
complete reply before deciding whether it's safe to speak at all — checking and then
un-speaking already-synthesized audio isn't possible, so the check has to happen before
synthesis starts, not after. `model_ttft` is still measured accurately (from the model's first
streamed token), it's just not the moment audio synthesis begins any more; that moment is now
`prompt_assemble`-adjacent, right after this function returns a checked, final string. See
docs/decisions/0010 for why `model_calls.cached` is always written `False` for Groq specifically.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import litellm

from ..core.config import get_settings
from ..core.logging import get_logger
from .prompt import DynamicContext, PersonaContext, assemble_messages
from .safety import check_reply, pick_canned_deflection

logger = get_logger(__name__)

MAX_GENERATION_ATTEMPTS = 2  # Task 2.3e: "regenerate once"

_REINFORCEMENT_EMPTY = (
    "Your previous reply was empty. Respond in character now, in a few words at least."
)
_REINFORCEMENT_VIOLATION = (
    "Your previous reply broke character, asked more than one question, or referred to "
    "scoring, evaluation, rubrics, or criteria. Regenerate: stay strictly in character, ask "
    "exactly one question, and never mention how the candidate is being assessed."
)

_CLAUSE_BOUNDARY = re.compile(r"[.!?](?=\s|$)")


def trim_to_last_complete_clause(text: str) -> str:
    """Task 2.3's edge case: "Model exceeds the word cap -> max_tokens truncates mid-sentence
    -> trim to the last complete clause before synthesis." If the text already ends cleanly,
    it's returned unchanged; otherwise it's cut back to the last sentence-ending punctuation
    found. If none exists at all (a single very long clause got cut), the text is returned
    as-is — sending a slightly-too-long fragment beats sending nothing."""
    stripped = text.rstrip()
    if not stripped:
        return stripped
    if stripped[-1] in ".!?":
        return stripped
    matches = list(_CLAUSE_BOUNDARY.finditer(stripped))
    if not matches:
        return stripped
    end = matches[-1].end()
    return stripped[:end].rstrip()


@dataclass(frozen=True, slots=True)
class PersonaReplyResult:
    text: str
    ttft_ms: float | None
    total_latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_cents: float
    cached: bool  # always False for Groq — see docs/decisions/0010
    attempts: int
    used_canned_deflection: bool
    violations: list[str]


async def _stream_full_reply(
    model: str, messages: list[dict[str, str]], max_tokens: int
) -> tuple[str, float | None, dict[str, Any]]:
    """Returns `(full_text, ttft_ms, raw_usage_and_cost)`. Streams so TTFT is measured from the
    model's actual first token, even though nothing is forwarded downstream until the whole
    reply is checked."""
    t0 = time.perf_counter()
    ttft_ms: float | None = None
    parts: list[str] = []
    usage: dict[str, Any] = {"tokens_in": 0, "tokens_out": 0, "cost_cents": 0.0}
    extra: dict[str, Any] = {}
    if litellm.supports_reasoning(model):
        # On a reasoning model `max_tokens` bounds reasoning tokens as well as content, so the
        # turn budget that exists to cap the persona's *spoken* length is partly spent thinking,
        # and every reasoning token is generated before the first word anyone can hear. Measured
        # against `groq/openai/gpt-oss-20b` on 2026-09-27, one short prompt, 6 calls each:
        # uncapped 51-91 reasoning tokens per reply, `low` 8-11. That is latency the user waits
        # through for text they never receive, on a path whose whole budget is 1400 ms.
        #
        # Honesty note, because the first version of this comment claimed more: this was written
        # while diagnosing 48 apparently-empty generations in a Level 2 run, and those turned out
        # to be Groq rate-limit errors, not token starvation (which is why `generation_error:*` is
        # now a distinct violation reason below). The reasoning-token measurement above is real and
        # the TTFT argument stands on its own; the effect on empty replies is NOT measured, and no
        # end-to-end TTFT comparison has been run against the hosted model because the daily quota
        # is exhausted. Non-reasoning models (the local Ollama persona) never see this parameter.
        extra["reasoning_effort"] = get_settings().persona_reasoning_effort
    stream = await litellm.acompletion(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=max_tokens,
        **extra,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            if ttft_ms is None:
                ttft_ms = (time.perf_counter() - t0) * 1000
            parts.append(delta)
        if getattr(chunk, "usage", None):
            usage["tokens_in"] = int(chunk.usage.prompt_tokens or 0)
            usage["tokens_out"] = int(chunk.usage.completion_tokens or 0)

    full_text = "".join(parts)
    try:
        # litellm.completion_cost has no token-count-only overload — it prices from the actual
        # message/completion text (or a full response object), so the real text is what's
        # passed, not the token counts captured above.
        cost = litellm.completion_cost(model=model, messages=messages, completion=full_text)
        usage["cost_cents"] = round(float(cost or 0.0) * 100, 6)
    except Exception:
        usage["cost_cents"] = 0.0
    return full_text, ttft_ms, usage


async def generate_persona_reply(
    *,
    model: str,
    max_tokens: int,
    persona_context: PersonaContext,
    dynamic_context: DynamicContext,
    static_prompt_text: str,
    turn_index: int,
) -> PersonaReplyResult:
    """The whole of Task 2.3e in one call: assemble, generate, enforce the word cap, run the
    post-generation check, regenerate once if needed, and fall back to a canned in-character
    deflection if it still fails. Never raises — every failure mode (empty reply, model error,
    repeated safety violation) resolves to a valid, speakable `PersonaReplyResult`."""
    base_messages = assemble_messages(persona_context, dynamic_context)
    reinforcement: str | None = None
    t_start = time.perf_counter()
    last_ttft_ms: float | None = None
    last_usage: dict[str, Any] = {"tokens_in": 0, "tokens_out": 0, "cost_cents": 0.0}
    all_violations: list[str] = []

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        messages = list(base_messages)
        if reinforcement:
            messages.append({"role": "system", "content": reinforcement})
        generation_error: str | None = None
        try:
            text, ttft_ms, usage = await _stream_full_reply(model, messages, max_tokens)
        except Exception as exc:
            generation_error = type(exc).__name__
            logger.warning(
                "persona_generation_failed", model=model, attempt=attempt, error=generation_error
            )
            text, ttft_ms, usage = "", None, last_usage
        last_ttft_ms, last_usage = ttft_ms, usage

        if not text.strip():
            # `generation_error:*` and `empty_reply` are deliberately different reasons. They were
            # the same reason (`empty_reply`) until 2026-09-27, and that cost real time and
            # produced a wrong answer: a Level 2 run (eval_runs 01a0e409) recorded 48 empty
            # generations in 72 replies and the natural reading was that the model had been
            # starved of output tokens by its own reasoning. They were Groq rate-limit errors. A
            # provider outage and a model that genuinely said nothing need completely different
            # fixes, an evaluation that cannot tell them apart will publish a number about the
            # wrong thing, and this is the second hosted Level 2 run to be invalidated by exactly
            # that confusion (the first is in README's Level 2 section, 2026-09-16).
            all_violations.append(
                f"generation_error:{generation_error}" if generation_error else "empty_reply"
            )
            reinforcement = _REINFORCEMENT_EMPTY
            continue

        text = trim_to_last_complete_clause(text)
        violations = check_reply(text, static_prompt_text)
        if not violations:
            return PersonaReplyResult(
                text=text,
                ttft_ms=last_ttft_ms,
                total_latency_ms=(time.perf_counter() - t_start) * 1000,
                tokens_in=int(last_usage["tokens_in"]),
                tokens_out=int(last_usage["tokens_out"]),
                cost_cents=float(last_usage["cost_cents"]),
                cached=False,
                attempts=attempt + 1,
                used_canned_deflection=False,
                # Violations from any *earlier*, discarded attempt this turn — Task 2.3's
                # edge case wants a `character_break` logged for evaluation even when the
                # retry itself came back clean and is what's actually spoken.
                violations=list(all_violations),
            )
        all_violations.extend(violations)
        logger.warning("persona_reply_check_failed", violations=violations, attempt=attempt)
        reinforcement = _REINFORCEMENT_VIOLATION

    deflection = pick_canned_deflection(turn_index)
    return PersonaReplyResult(
        text=deflection,
        ttft_ms=last_ttft_ms,
        total_latency_ms=(time.perf_counter() - t_start) * 1000,
        tokens_in=int(last_usage["tokens_in"]),
        tokens_out=int(last_usage["tokens_out"]),
        cost_cents=float(last_usage["cost_cents"]),
        cached=False,
        attempts=MAX_GENERATION_ATTEMPTS,
        used_canned_deflection=True,
        violations=all_violations,
    )
