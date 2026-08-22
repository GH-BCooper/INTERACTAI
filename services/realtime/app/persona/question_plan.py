"""docs/phase-2-BUILD.md TASK 2.3b: the question plan. Generated once at session start by
`MODEL_PLANNER`, off the critical path; updated after every turn. `sessions.question_plan`
(the DB column) is the durable mirror, checkpointed periodically — the in-memory copy on
`SessionRuntime.question_plan` is authoritative while the session is live (session.py's own
docstring makes the same point about every other piece of runtime state).
"""

from __future__ import annotations

from typing import Any, Literal

import litellm
from pydantic import BaseModel, Field

from ..core.logging import get_logger

logger = get_logger(__name__)

Depth = Literal["shallow", "medium", "deep"]
TopicStatus = Literal["pending", "active", "done"]


class PlanTopicOut(BaseModel):
    id: str
    topic: str
    depth: Depth = "medium"
    minutes: int = Field(ge=1, default=5)


class QuestionPlanOutput(BaseModel):
    topics: list[PlanTopicOut]


_PLANNER_SYSTEM_PROMPT = (
    "You plan the topic sequence for a practice interview session. Given the scenario brief, "
    "the candidate's resume text (if any), and any focus areas they requested, produce a short "
    "ordered list of topics to cover, each with a rough time allocation that sums to "
    "approximately the session's target length. 3-6 topics is typical for a short session, "
    "more for a longer one. Do not write questions — just topic labels a real interviewer "
    "would use to plan their own session, e.g. 'system design tradeoffs' or 'a time they "
    "disagreed with a teammate,' not full sentences."
)


def _fallback_plan(opening_strategy: str, target_minutes: int) -> dict[str, Any]:
    """Task 2.3b: "Plan generation failure must not block the session. Fall back to the
    scenario's opening_strategy plus generic topic progression, and log it." One topic, the
    whole session — crude, but the persona still has `opening_strategy` in the brief layer
    regardless, so conversation quality degrades gracefully, not to a crash."""
    return {
        "topics": [
            {
                "id": "t0",
                "topic": opening_strategy,
                "depth": "medium",
                "minutes": target_minutes,
                "status": "active",
                "followups_used": 0,
            }
        ],
        "elapsed_minutes": 0,
        "pending_obligation": None,
    }


async def generate_question_plan(
    model: str,
    *,
    scenario_brief: str,
    opening_strategy: str,
    resume_text: str | None,
    focus_areas: list[str],
    target_minutes: int,
) -> dict[str, Any]:
    """Returns the dict shape stored in `question_plan` / `sessions.question_plan`. Never
    raises — any failure (timeout, bad output, model error) logs and falls back."""
    user_parts = [f"Scenario brief:\n{scenario_brief}", f"Target length: {target_minutes} minutes."]
    if resume_text:
        user_parts.append(f"Candidate resume notes:\n{resume_text}")
    if focus_areas:
        user_parts.append(f"Requested focus areas: {', '.join(focus_areas)}")

    try:
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            response_format=QuestionPlanOutput,
            timeout=10.0,
        )
        parsed = QuestionPlanOutput.model_validate_json(response.choices[0].message.content)
        if not parsed.topics:
            raise ValueError("planner returned zero topics")
        topics = [
            {
                "id": t.id,
                "topic": t.topic,
                "depth": t.depth,
                "minutes": t.minutes,
                "status": "active" if i == 0 else "pending",
                "followups_used": 0,
            }
            for i, t in enumerate(parsed.topics)
        ]
        return {"topics": topics, "elapsed_minutes": 0, "pending_obligation": None}
    except Exception:
        logger.warning("question_plan_generation_failed", model=model)
        return _fallback_plan(opening_strategy, target_minutes)


def current_topic(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan:
        return None
    topics: list[dict[str, Any]] = plan.get("topics", [])
    for topic in topics:
        if topic.get("status") == "active":
            return topic
    return None


def advance_plan(
    plan: dict[str, Any], *, followups_cap: int, answer_was_vague: bool, obligation: str | None
) -> dict[str, Any]:
    """Task 2.3b: "Updated after every turn: advance on a strong answer, increment
    followups_used on a vague one, set pending_obligation when the persona asked for something
    specific and did not get it." Pure — returns a new plan dict, never mutates the input, so
    callers control exactly when the change becomes visible/persisted."""
    topics = [dict(t) for t in plan.get("topics", [])]
    active_idx = next((i for i, t in enumerate(topics) if t.get("status") == "active"), None)

    if active_idx is not None:
        active = topics[active_idx]
        if answer_was_vague:
            active["followups_used"] = int(active.get("followups_used", 0)) + 1
            if active["followups_used"] >= followups_cap:
                active["status"] = "done"
                _activate_next(topics, active_idx)
        else:
            active["status"] = "done"
            _activate_next(topics, active_idx)

    return {
        "topics": topics,
        "elapsed_minutes": plan.get("elapsed_minutes", 0),
        "pending_obligation": obligation,
    }


def _activate_next(topics: list[dict[str, Any]], done_idx: int) -> None:
    for i in range(done_idx + 1, len(topics)):
        if topics[i].get("status") == "pending":
            topics[i]["status"] = "active"
            return


def is_plan_exhausted(plan: dict[str, Any] | None) -> bool:
    """Task 2.3's edge case: "Question plan exhausted early -> Persona wraps up gracefully
    rather than inventing filler." """
    if not plan:
        return False
    return all(t.get("status") == "done" for t in plan.get("topics", []))
