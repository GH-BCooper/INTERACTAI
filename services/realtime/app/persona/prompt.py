"""docs/phase-2-BUILD.md TASK 2.3a: layered prompt assembly. "Assembly order is load-bearing.
Static -> semi-static -> dynamic, in that order, with cache-control markers on the first two.
Anything variable placed above them destroys prefix caching silently."

The "cache-control markers" are the message boundaries themselves: static and brief are each
their own `system` message, always rendered byte-identical for a given session (brief is
compiled once and never changes; static never changes across the whole codebase), so a
provider with automatic prefix caching (Groq) sees the same token prefix on every call for this
session and can hit its cache — no explicit annotation needed or available on this API shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .difficulty import DifficultyParams, parse_difficulty_params, render_difficulty_instructions

_PROMPTS_DIR = Path(__file__).resolve().parents[4] / "content" / "prompts" / "persona"


def _load_static_prompt(path: Path) -> tuple[str, str]:
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


STATIC_VERSION, STATIC_TEXT = _load_static_prompt(_PROMPTS_DIR / "static.v1.md")

_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,  # noqa: S701 — plain text prompts, not HTML; escaping would corrupt them
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
)
_BRIEF_TEMPLATE = _JINJA_ENV.get_template("brief.v1.jinja")
_DYNAMIC_TEMPLATE = _JINJA_ENV.get_template("dynamic.v1.jinja")
BRIEF_VERSION = "1.0.0"
DYNAMIC_VERSION = "1.0.0"
PROMPT_VERSION = f"static:{STATIC_VERSION}+brief:{BRIEF_VERSION}+dynamic:{DYNAMIC_VERSION}"


@dataclass(frozen=True, slots=True)
class PersonaContext:
    """Everything needed to render the semi-static brief layer — compiled once per session
    from `sessions.brief` (frozen at session creation, docs/phase-0-BUILD.md TASK 0.5), never
    recomputed mid-session."""

    persona_name: str
    persona_archetype: str
    persona_temperament: str
    persona_brief: str
    scenario_brief: str
    opening_strategy: str
    target_minutes: int
    difficulty: DifficultyParams
    focus_areas: list[str] = field(default_factory=list)
    # Task 2.3b's question planner considers this; the brief/dynamic prompt layers do not — the
    # candidate's resume text was never meant to be read back to them.
    resume_text: str | None = None


def build_persona_context_from_brief(brief: dict[str, Any]) -> PersonaContext:
    """`brief` is `sessions.brief` (the frozen JSONB row) — see
    `services/api/app/services/session_service.py::_compile_brief` for exactly what's in it.
    Every field read here is a plain fallback-safe `.get()`: a session created before a given
    brief field existed (or a malformed one from a bug) degrades to something speakable rather
    than crashing the handshake."""
    return PersonaContext(
        persona_name=brief.get("persona_name") or "the interviewer",
        persona_archetype=brief.get("persona_archetype") or "interviewer",
        persona_temperament=brief.get("persona_temperament") or "neutral",
        persona_brief=brief.get("persona_brief") or "",
        scenario_brief=brief.get("scenario_brief") or "",
        opening_strategy=brief.get("opening_strategy") or "",
        target_minutes=int(brief.get("target_minutes") or 15),
        difficulty=parse_difficulty_params(
            brief.get("difficulty_params") or {"ack_length": "short"}
        ),
        focus_areas=list(brief.get("focus_areas") or []),
        resume_text=brief.get("resume_text_snapshot") or None,
    )


@dataclass(frozen=True, slots=True)
class DynamicContext:
    """Everything needed to render the per-turn dynamic layer."""

    candidate_speech: str
    recent_turns: list[dict[str, str]] = field(default_factory=list)
    history_summary: str = ""
    elapsed_minutes: int | None = None
    target_minutes: int | None = None
    plan_topic: str | None = None
    pending_obligation: str | None = None


def render_brief(ctx: PersonaContext) -> str:
    rendered: str = _BRIEF_TEMPLATE.render(
        persona_name=ctx.persona_name,
        persona_archetype=ctx.persona_archetype,
        persona_temperament=ctx.persona_temperament,
        persona_brief=ctx.persona_brief,
        scenario_brief=ctx.scenario_brief,
        opening_strategy=ctx.opening_strategy,
        difficulty_instructions=render_difficulty_instructions(ctx.difficulty),
        target_minutes=ctx.target_minutes,
        focus_areas=ctx.focus_areas,
    )
    return rendered.strip()


def render_dynamic(ctx: DynamicContext) -> str:
    rendered: str = _DYNAMIC_TEMPLATE.render(
        candidate_speech=ctx.candidate_speech,
        recent_turns=ctx.recent_turns,
        history_summary=ctx.history_summary,
        elapsed_minutes=ctx.elapsed_minutes,
        target_minutes=ctx.target_minutes,
        plan_topic=ctx.plan_topic,
        pending_obligation=ctx.pending_obligation,
    )
    return rendered.strip()


def assemble_messages(
    persona_context: PersonaContext, dynamic_context: DynamicContext
) -> list[dict[str, str]]:
    """Static -> brief -> dynamic, in that order (Task 2.3a). Three separate messages, not one
    concatenated string, so the boundary between the always-identical prefix (static+brief) and
    the always-different suffix (dynamic) is unambiguous to both the provider's cache and to
    anyone reading a `model_calls` trace later."""
    return [
        {"role": "system", "content": STATIC_TEXT},
        {"role": "system", "content": render_brief(persona_context)},
        {"role": "user", "content": render_dynamic(dynamic_context)},
    ]
