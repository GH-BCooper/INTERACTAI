"""docs/phase-2-BUILD.md TASK 2.3b: the question plan's pure update logic. Generation itself
(the live MODEL_PLANNER call) is exercised in test_persona_live.py; this file covers the
fallback and the advance/exhaustion state machine, which need no model at all."""

from __future__ import annotations

from services.realtime.app.persona.question_plan import (
    _fallback_plan,
    advance_plan,
    current_topic,
    is_plan_exhausted,
)


def _plan(*topics: dict[str, object]) -> dict[str, object]:
    return {"topics": list(topics), "elapsed_minutes": 0, "pending_obligation": None}


class TestFallbackPlan:
    def test_fallback_has_one_active_topic_from_opening_strategy(self) -> None:
        plan = _fallback_plan("Ask about their hardest project.", 10)
        assert len(plan["topics"]) == 1
        topic = plan["topics"][0]
        assert topic["status"] == "active"
        assert topic["topic"] == "Ask about their hardest project."
        assert topic["minutes"] == 10


class TestCurrentTopic:
    def test_returns_the_active_topic(self) -> None:
        plan = _plan(
            {"id": "a", "topic": "warm-up", "status": "done", "followups_used": 0},
            {"id": "b", "topic": "system design", "status": "active", "followups_used": 0},
            {"id": "c", "topic": "wrap-up", "status": "pending", "followups_used": 0},
        )
        assert current_topic(plan)["id"] == "b"

    def test_no_active_topic_returns_none(self) -> None:
        plan = _plan({"id": "a", "topic": "x", "status": "done", "followups_used": 0})
        assert current_topic(plan) is None

    def test_none_plan_returns_none(self) -> None:
        assert current_topic(None) is None


class TestAdvancePlan:
    def test_strong_answer_advances_to_next_topic(self) -> None:
        plan = _plan(
            {"id": "a", "topic": "first", "status": "active", "followups_used": 0},
            {"id": "b", "topic": "second", "status": "pending", "followups_used": 0},
        )
        updated = advance_plan(plan, followups_cap=1, answer_was_vague=False, obligation=None)
        assert updated["topics"][0]["status"] == "done"
        assert updated["topics"][1]["status"] == "active"

    def test_vague_answer_increments_followups_without_advancing(self) -> None:
        plan = _plan({"id": "a", "topic": "first", "status": "active", "followups_used": 0})
        updated = advance_plan(plan, followups_cap=3, answer_was_vague=True, obligation=None)
        assert updated["topics"][0]["status"] == "active"
        assert updated["topics"][0]["followups_used"] == 1

    def test_vague_answer_at_followups_cap_advances_anyway(self) -> None:
        """Task 2.3c's own gentle/standard/hard followups_on_vague values are a *cap*, not an
        infinite allowance — once used up, the plan still has to move on."""
        plan = _plan(
            {"id": "a", "topic": "first", "status": "active", "followups_used": 2},
            {"id": "b", "topic": "second", "status": "pending", "followups_used": 0},
        )
        updated = advance_plan(plan, followups_cap=3, answer_was_vague=True, obligation=None)
        assert updated["topics"][0]["status"] == "done"
        assert updated["topics"][1]["status"] == "active"

    def test_pending_obligation_is_recorded(self) -> None:
        plan = _plan({"id": "a", "topic": "first", "status": "active", "followups_used": 0})
        updated = advance_plan(
            plan, followups_cap=1, answer_was_vague=False, obligation="the actual throughput number"
        )
        assert updated["pending_obligation"] == "the actual throughput number"

    def test_advance_plan_does_not_mutate_the_input(self) -> None:
        plan = _plan({"id": "a", "topic": "first", "status": "active", "followups_used": 0})
        advance_plan(plan, followups_cap=1, answer_was_vague=False, obligation=None)
        assert plan["topics"][0]["status"] == "active"  # original untouched

    def test_last_topic_done_leaves_nothing_active(self) -> None:
        plan = _plan({"id": "a", "topic": "only", "status": "active", "followups_used": 0})
        updated = advance_plan(plan, followups_cap=1, answer_was_vague=False, obligation=None)
        assert current_topic(updated) is None


class TestIsPlanExhausted:
    def test_all_done_is_exhausted(self) -> None:
        plan = _plan(
            {"id": "a", "topic": "x", "status": "done", "followups_used": 0},
            {"id": "b", "topic": "y", "status": "done", "followups_used": 0},
        )
        assert is_plan_exhausted(plan) is True

    def test_one_active_is_not_exhausted(self) -> None:
        plan = _plan(
            {"id": "a", "topic": "x", "status": "done", "followups_used": 0},
            {"id": "b", "topic": "y", "status": "active", "followups_used": 0},
        )
        assert is_plan_exhausted(plan) is False

    def test_none_plan_is_not_exhausted(self) -> None:
        assert is_plan_exhausted(None) is False
