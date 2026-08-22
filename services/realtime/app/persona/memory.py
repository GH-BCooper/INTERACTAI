"""docs/phase-2-BUILD.md TASK 2.3d: memory compaction. Recent 6 turns verbatim; older turns
replaced by a running summary, regenerated every 6 turns by `MODEL_NARRATOR` — "during
listening, never during thinking. Compaction time during listening is free; the same work
during thinking comes straight out of the latency budget." This module's public function is
therefore called as a fire-and-forget background task from the listening-state code path
(frame_pipeline.py), never awaited inline from the turn pipeline (turn.py).
"""

from __future__ import annotations

import litellm

from ..core.logging import get_logger

logger = get_logger(__name__)

RECENT_TURNS_VERBATIM = 6

_SUMMARY_SYSTEM_PROMPT = (
    "Summarize a practice-interview conversation so far, for use as context in later turns of "
    "the same conversation. Record: topics already covered, your impression of answer quality "
    "per topic (specific and well-supported vs vague and unsupported), and anything the "
    "candidate was asked for but has not yet provided. Write it as plain notes, not prose — "
    "third person, terse, no more than 6 sentences. This is a private note for continuing the "
    "conversation, not something ever shown to the candidate."
)


def split_recent_and_older(
    history: list[dict[str, str]], *, recent_n: int = RECENT_TURNS_VERBATIM
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Pure split — `history` is `[{"speaker": "user"|"persona", "text": str}, ...]` in order.
    Returns `(older, recent)`."""
    if len(history) <= recent_n:
        return [], history
    return history[:-recent_n], history[-recent_n:]


def _format_turns(turns: list[dict[str, str]]) -> str:
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)


async def summarize_history(
    model: str, *, previous_summary: str, older_turns: list[dict[str, str]]
) -> str:
    """Never raises — a failed compaction just means the next call carries the previous summary
    forward unchanged (Task 2.3's general pattern: a missing optimization degrades quality, it
    never breaks the session)."""
    if not older_turns:
        return previous_summary
    parts = []
    if previous_summary:
        parts.append(f"Summary so far: {previous_summary}")
    parts.append(f"New turns to fold in:\n{_format_turns(older_turns)}")
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": "\n\n".join(parts)},
            ],
            timeout=10.0,
            max_tokens=200,
        )
        content = response.choices[0].message.content
        return content.strip() if content else previous_summary
    except Exception:
        logger.warning("history_compaction_failed", model=model)
        return previous_summary
