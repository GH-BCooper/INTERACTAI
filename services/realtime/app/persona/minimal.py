"""The minimal persona (Task 1.6c) — deliberately trivial. A single-layer prompt, no question
plan, no difficulty ladder (all Phase 2, docs/phase-2-BUILD.md). Just enough to produce a
short in-character reply so the CLI harness closes the loop end to end. Resist improving it
here — that is explicitly out of scope for this task.

The prompt itself is a versioned content artefact (CLAUDE.md §11), never a string literal —
see content/prompts/persona-minimal.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import litellm

_PROMPT_PATH = Path(__file__).resolve().parents[4] / "content" / "prompts" / "persona-minimal.md"


def _load_prompt(path: Path = _PROMPT_PATH) -> tuple[str, str]:
    """Returns `(version, prompt_body)`, stripping the YAML front matter."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return "0.0.0", raw.strip()
    _marker, front_matter, body = raw.split("---", 2)
    version = "0.0.0"
    for line in front_matter.splitlines():
        stripped = line.strip()
        if stripped.startswith("version:"):
            version = stripped.split(":", 1)[1].strip().strip('"')
            break
    return version, body.strip()


PROMPT_VERSION, PROMPT_TEXT = _load_prompt()


def build_messages(user_text: str) -> list[dict[str, str]]:
    """User speech is untrusted content, delimited and labelled (CLAUDE.md §7) — never
    concatenated into the system prompt, always its own clearly-tagged turn."""
    return [
        {"role": "system", "content": PROMPT_TEXT},
        {"role": "user", "content": f"<candidate_speech>{user_text}</candidate_speech>"},
    ]


async def stream_reply(model: str, user_text: str) -> AsyncIterator[str]:
    """Yields text deltas as they stream in. Token/timing/cost accounting for `model_calls`
    is the caller's responsibility (it needs the surrounding turn/session context this
    function doesn't have) — see services/realtime/app/metrics/model_calls.py."""
    response = await litellm.acompletion(
        model=model,
        messages=build_messages(user_text),
        stream=True,
        max_tokens=180,
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def canned_stub_reply(turn_index: int) -> str:
    """`--persona-stub` mode (Task 1.6b): a fixed canned reply that isolates pipeline latency
    from model latency. Deliberately not streamed token-by-token — it exists to prove the
    chunker/TTS/playback path works without waiting on a real model."""
    replies = [
        "Thanks for sharing that. What made that particular challenge stick with you?",
        "That's a good example. How did the rest of the team respond to that change?",
        "I see. What would you do differently if you ran into that again?",
    ]
    return replies[turn_index % len(replies)]
