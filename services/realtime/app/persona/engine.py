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
    stream = await litellm.acompletion(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=max_tokens,
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
        try:
            text, ttft_ms, usage = await _stream_full_reply(model, messages, max_tokens)
        except Exception:
            logger.warning("persona_generation_failed", model=model, attempt=attempt)
            text, ttft_ms, usage = "", None, last_usage
        last_ttft_ms, last_usage = ttft_ms, usage

        if not text.strip():
            all_violations.append("empty_reply")
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
