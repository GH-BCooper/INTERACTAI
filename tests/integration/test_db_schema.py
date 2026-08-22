"""Task 0.4 acceptance criteria — docs/phase-0-BUILD.md.

Real Postgres via testcontainers (tests/integration/conftest.py), migrated with the actual
Alembic revision, not a hand-rolled schema. If the migration is wrong, these fail.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.models import (
    Annotation,
    LatencyEvent,
    ModelCall,
    Profile,
    Report,
    Rubric,
    RubricCriterion,
    Scenario,
    SessionScore,
    Turn,
    TurnMetrics,
    TurnScore,
    User,
)
from services.api.app.models import (
    Session as SessionModel,
)

VALID_ANCHORS = {
    "1": "No discernible organisation. The answer starts mid-thought or never resolves.",
    "2": "Facts in the order they occurred to the speaker; no signposting at all here.",
    "3": "Recognisable beginning and end, but the middle wanders noticeably throughout.",
    "4": "A clear arc with one weak transition or a missing close, still easy to follow.",
    "5": "Opens by naming the situation, moves through action to outcome, closes cleanly.",
}

LONG_BRIEF = (
    "You are a staff engineer at a mid-size fintech, forty minutes into a day of "
    "back-to-back screens and slightly behind schedule. You care about whether the "
    "candidate has actually operated a system in production, and you are unimpressed by "
    "framework name-dropping. You have a hard stop in twenty minutes."
)


async def _make_user(db_session: AsyncSession, email: str = "a@example.com") -> User:
    user = User(email=email)
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_rubric_with_criterion(db_session: AsyncSession) -> tuple[Rubric, RubricCriterion]:
    rubric = Rubric(slug="general_interview", name="General interview", description="x")
    db_session.add(rubric)
    await db_session.flush()
    criterion = RubricCriterion(
        rubric_id=rubric.id,
        key="structure",
        name="Structure",
        description="Does the answer have a discernible arc?",
        anchor_descriptors=VALID_ANCHORS,
    )
    db_session.add(criterion)
    await db_session.flush()
    return rubric, criterion


async def _make_scenario(db_session: AsyncSession) -> Scenario:
    scenario = Scenario(
        slug="technical-standard",
        family="technical",
        difficulty="standard",
        title="Backend engineer, system design screen",
        brief=LONG_BRIEF,
        opening_strategy="Open with a brief thanks, then ask about the hardest thing shipped.",
        difficulty_params={"standard": {"followups_on_vague": 1}},
    )
    db_session.add(scenario)
    await db_session.flush()
    return scenario


async def _make_session(db_session: AsyncSession, user: User, scenario: Scenario) -> SessionModel:
    session_row = SessionModel(
        user_id=user.id,
        scenario_id=scenario.id,
        target_minutes=10,
        brief={"persona_prompt_ref": "x", "rubric_id": "x"},
    )
    db_session.add(session_row)
    await db_session.flush()
    return session_row


async def _make_turn(
    db_session: AsyncSession, session_row: SessionModel, index: int, created_at: datetime
) -> Turn:
    turn = Turn(
        session_id=session_row.id,
        index=index,
        speaker="user",
        text="hello",
        start_ms=0,
        end_ms=100,
        created_at=created_at,
    )
    db_session.add(turn)
    await db_session.flush()
    return turn


class TestRubricCriteriaAnchorDescriptors:
    async def test_rejects_missing_scale_point(self, db_session: AsyncSession) -> None:
        rubric = Rubric(slug="r1", name="R1", description="x")
        db_session.add(rubric)
        await db_session.flush()

        incomplete = dict(VALID_ANCHORS)
        del incomplete["5"]

        db_session.add(
            RubricCriterion(
                rubric_id=rubric.id,
                key="structure",
                name="Structure",
                description="x",
                anchor_descriptors=incomplete,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_rejects_empty_anchor_descriptors(self, db_session: AsyncSession) -> None:
        rubric = Rubric(slug="r2", name="R2", description="x")
        db_session.add(rubric)
        await db_session.flush()

        db_session.add(
            RubricCriterion(
                rubric_id=rubric.id,
                key="structure",
                name="Structure",
                description="x",
                anchor_descriptors={},
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_accepts_complete_anchor_descriptors(self, db_session: AsyncSession) -> None:
        rubric, criterion = await _make_rubric_with_criterion(db_session)
        assert criterion.id is not None


class TestTurnsDuplicateIndex:
    async def test_rejects_duplicate_session_index(self, db_session: AsyncSession) -> None:
        user = await _make_user(db_session)
        scenario = await _make_scenario(db_session)
        session_row = await _make_session(db_session, user, scenario)

        # created_at is passed explicitly (not left to the server default) so both rows land
        # in the same instant — the constraint is (session_id, index, created_at); see
        # docs/decisions/0002-turns-partitioning-and-fk.md for why created_at is in it at all.
        same_instant = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
        await _make_turn(db_session, session_row, index=0, created_at=same_instant)

        db_session.add(
            Turn(
                session_id=session_row.id,
                index=0,
                speaker="persona",
                text="hi again",
                start_ms=0,
                end_ms=50,
                created_at=same_instant,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestUserDeletionCascade:
    async def test_deleting_a_user_leaves_zero_orphans(self, db_session: AsyncSession) -> None:
        user = await _make_user(db_session, email="orphan-check@example.com")
        db_session.add(Profile(user_id=user.id, resume_text="I did things."))
        scenario = await _make_scenario(db_session)
        session_row = await _make_session(db_session, user, scenario)
        turn = await _make_turn(db_session, session_row, index=0, created_at=datetime.now(UTC))

        db_session.add(
            TurnMetrics(
                session_id=session_row.id,
                turn_id=turn.id,
                wpm=120,
                filler_count=0,
                filler_rate=0,
                longest_pause_ms=0,
                speech_ratio=1,
                word_count=10,
            )
        )
        db_session.add(
            TurnScore(
                session_id=session_row.id,
                turn_id=turn.id,
                criterion_key="structure",
                score=4,
                confidence=0.9,
                evidence_spans=[],
                model_version="v1",
            )
        )
        db_session.add(
            SessionScore(
                session_id=session_row.id,
                criterion_key="structure",
                aggregate_score=4,
                confidence=0.9,
                model_version="v1",
            )
        )
        db_session.add(Report(session_id=session_row.id, status="pending"))
        db_session.add(
            LatencyEvent(session_id=session_row.id, turn_id=turn.id, stage="e2e", duration_ms=1200)
        )
        db_session.add(
            ModelCall(
                session_id=session_row.id,
                turn_id=turn.id,
                role="persona",
                model="groq/x",
                tokens_in=10,
                tokens_out=10,
                total_latency_ms=500,
            )
        )
        db_session.add(
            Annotation(
                session_id=session_row.id,
                turn_id=turn.id,
                annotator_id=user.id,
                criterion_key="structure",
                score=4,
            )
        )
        await db_session.flush()

        await db_session.delete(user)
        await db_session.flush()

        checks = [
            (Profile, Profile.user_id == user.id),
            (SessionModel, SessionModel.user_id == user.id),
            (TurnMetrics, TurnMetrics.session_id == session_row.id),
            (TurnScore, TurnScore.session_id == session_row.id),
            (SessionScore, SessionScore.session_id == session_row.id),
            (Report, Report.session_id == session_row.id),
            (LatencyEvent, LatencyEvent.session_id == session_row.id),
            (ModelCall, ModelCall.session_id == session_row.id),
            (Annotation, Annotation.session_id == session_row.id),
        ]
        for model, predicate in checks:
            count = await db_session.scalar(
                select(func.count()).select_from(model).where(predicate)
            )
            assert count == 0, f"{model.__tablename__} has orphaned rows after user deletion"

        turn_count = await db_session.scalar(
            select(func.count()).select_from(Turn).where(Turn.session_id == session_row.id)
        )
        assert turn_count == 0


class TestTurnsIndexUsage:
    async def test_last_20_by_index_uses_the_index(self, db_session: AsyncSession) -> None:
        user = await _make_user(db_session, email="perf@example.com")
        scenario = await _make_scenario(db_session)
        session_row = await _make_session(db_session, user, scenario)
        await db_session.flush()

        # Bulk insert 1,000 turns — one per second starting now, so every row lands in a
        # distinct, already-created monthly partition (or the DEFAULT one) without per-row
        # ORM overhead.
        await db_session.execute(
            text(
                """
                INSERT INTO turns (id, created_at, updated_at, session_id, "index", speaker,
                                    text, start_ms, end_ms, word_timings, truncated)
                SELECT gen_random_uuid(), now(), now(), :session_id, g, 'user', 'hi',
                       0, 100, '[]'::jsonb, false
                FROM generate_series(0, 999) AS g
                """
            ),
            {"session_id": str(session_row.id)},
        )
        await db_session.flush()

        result = await db_session.execute(
            text(
                """
                EXPLAIN (FORMAT JSON)
                SELECT * FROM turns WHERE session_id = :session_id
                ORDER BY "index" DESC LIMIT 20
                """
            ),
            {"session_id": str(session_row.id)},
        )
        plan = result.scalar()
        plan_text = str(plan)
        assert "Seq Scan" not in plan_text, f"expected an index scan, got: {plan_text}"
        assert "Index" in plan_text
