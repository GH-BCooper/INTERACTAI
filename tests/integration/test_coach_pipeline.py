"""docs/phase-2-BUILD.md TASK 2.5: the coach pipeline against a real database (testcontainers
Postgres, via the shared `tests/integration/conftest.py` fixtures — "never mock the thing under
test"). The scorer and narrator are the two pieces that genuinely need a network LLM call, so
this test injects fakes for exactly those two (their own logic is covered by
tests/unit/coach/*); everything else — DB reads/writes, upserts, idempotency, the real seeded
rubric's aggregation_policy — runs against the real schema.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

# `db_session`, `db_connection`, `seeded_content` come from the sibling conftest.py — pytest
# discovers it automatically for every test file in this directory, no explicit import needed.


@pytest.fixture
def coach_sessionmaker(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=db_connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )


@pytest.fixture(autouse=True)
def _patch_coach_sessionmaker(monkeypatch: pytest.MonkeyPatch, coach_sessionmaker: object) -> None:
    """`report/build.py` and `worker.py` each import `get_sessionmaker` into their own module
    namespace (`from ..db.session import get_sessionmaker`), so the patch target is each of
    those local bindings, not `db.session.get_sessionmaker` itself."""
    import services.coach.app.report.build as build_module

    monkeypatch.setattr(build_module, "get_sessionmaker", lambda: coach_sessionmaker)


class _FakeScorer:
    """A `Scorer` that returns a fixed, high-confidence score for every criterion, with a real
    (verified) evidence span sliced from the actual answer text — real evidence verification
    logic runs, just without a real model call."""

    version = "fake:1.0.0"

    async def score(self, question: str, answer: str, criterion: object) -> object:
        results = await self.score_batch(question, answer, [criterion])
        return results[0]

    async def score_batch(self, question: str, answer: str, criteria: list[object]) -> list[object]:
        from services.coach.app.scorer.base import CriterionScore
        from services.coach.app.scorer.evidence import verify_spans

        quote = answer[:20] if len(answer) >= 20 else answer
        verification = verify_spans(answer, [quote] if quote else [])
        return [
            CriterionScore(
                score=4.0,
                confidence=0.9,
                evidence_spans=verification.verified_spans,
                rationale="fake",
            )
            for _ in criteria
        ]


@pytest.fixture(autouse=True)
def _patch_scorer(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.coach.app.report.build as build_module

    monkeypatch.setattr(build_module, "get_scorer", lambda: _FakeScorer())


@pytest.fixture(autouse=True)
def _patch_narrator(monkeypatch: pytest.MonkeyPatch) -> None:
    """The narrator's own post-checks/blocklist/contradiction logic has its own unit tests
    (tests/unit/coach/test_narrator_checks.py); this integration test is about the DB pipeline
    around it, so a fast fake stands in rather than a real (slow, network-dependent) LLM call."""
    import services.coach.app.report.build as build_module

    async def _fake_generate_narrative(**kwargs: object) -> tuple[object, None]:
        from services.coach.app.narrator.narrator import NarrativeResult

        return (
            NarrativeResult(
                summary="fake summary",
                strengths=["fake strength"],
                growth_areas=["fake growth area"],
                next_actions=[{"text": "fake action", "turn_id": None}],
                model_version="fake-narrator:1.0.0",
            ),
            None,
        )

    monkeypatch.setattr(build_module, "generate_narrative", _fake_generate_narrative)


async def _seed_session_with_turns(
    db_session: AsyncSession, *, rubric_id: uuid.UUID, rubric_slug: str, n_user_turns: int
) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Real `users`/`scenarios`/`sessions`/`turns`/`turn_metrics` rows, minimal but real —
    exercising the actual FK/CHECK-constrained schema, not a mocked shape of it."""
    from services.api.app.models import Persona, Scenario, Session, Turn, TurnMetrics, User

    user = User(email=f"coach-test-{uuid.uuid4()}@example.com")
    persona = Persona(
        slug=f"p-{uuid.uuid4()}",
        name="Test Persona",
        archetype="interviewer",
        temperament="neutral",
        voice_id="en_US-lessac-medium",
        brief="A test persona brief used only by this integration test.",
    )
    db_session.add_all([user, persona])
    await db_session.flush()

    scenario = Scenario(
        slug=f"s-{uuid.uuid4()}",
        family="technical",
        difficulty="standard",
        title="Test scenario",
        brief="A" * 210,
        opening_strategy="Ask about a recent project.",
        difficulty_params={"standard": {}},
        persona_id=persona.id,
        rubric_id=rubric_id,
    )
    db_session.add(scenario)
    await db_session.flush()

    session = Session(
        user_id=user.id,
        scenario_id=scenario.id,
        status="active",
        target_minutes=10,
        focus_areas=[],
        brief={
            "rubric_id": str(rubric_id),
            "rubric_slug": rubric_slug,
            "opening_strategy": scenario.opening_strategy,
        },
    )
    db_session.add(session)
    await db_session.flush()

    # `turns` is unique on (session_id, index, created_at) with created_at server_default=now().
    # Postgres' now()/CURRENT_TIMESTAMP is transaction start time, constant for the whole
    # duration of this test's one transactional db_session fixture — relying on the server
    # default here would collide the moment two turns share an `index` (every real exchange:
    # services/realtime/app/turn.py persists the user turn and the persona reply with the same
    # `index`). Real traffic never hits this (each insert there is its own committed
    # transaction, so `now()` genuinely advances); this fixture sets explicit, distinct
    # timestamps instead of relying on real wall-clock separation between two flushes in one
    # transaction.
    base_time = datetime.now(UTC)
    turn_ids: list[uuid.UUID] = []
    for i in range(n_user_turns):
        persona_turn = Turn(
            session_id=session.id,
            created_at=base_time + timedelta(milliseconds=i * 10),
            index=i,
            speaker="persona",
            text=f"Tell me about project number {i}?",
            start_ms=i * 1000,
            end_ms=i * 1000 + 100,
            word_timings=[],
            truncated=False,
        )
        db_session.add(persona_turn)
        await db_session.flush()

        user_turn = Turn(
            session_id=session.id,
            created_at=base_time + timedelta(milliseconds=i * 10 + 5),
            index=i,
            speaker="user",
            text=(
                f"I rebuilt the ingestion pipeline using Kafka, project {i}, and it now "
                "handles 3000 events per second."
            ),
            start_ms=i * 1000 + 200,
            end_ms=i * 1000 + 900,
            word_timings=[],
            truncated=False,
            asr_confidence=0.95,
        )
        db_session.add(user_turn)
        await db_session.flush()
        turn_ids.append(user_turn.id)

        db_session.add(
            TurnMetrics(
                session_id=session.id,
                turn_id=user_turn.id,
                wpm=140.0,
                filler_count=0,
                filler_rate=0.0,
                longest_pause_ms=200,
                speech_ratio=0.9,
                word_count=20,
            )
        )
    await db_session.flush()
    return session.id, user.id, turn_ids


@pytest.mark.asyncio
async def test_score_turn_and_generate_report_full_pipeline(
    db_session: AsyncSession, seeded_content: dict[str, dict[str, object]]
) -> None:
    from services.coach.app.report.build import generate_report, score_turn

    rubric_ids = seeded_content["rubric_ids"]
    rubric_id = rubric_ids["general_interview"]
    session_id, _user_id, turn_ids = await _seed_session_with_turns(
        db_session, rubric_id=rubric_id, rubric_slug="general_interview", n_user_turns=3
    )
    await db_session.commit()

    for turn_id in turn_ids:
        await score_turn({}, session_id=str(session_id), turn_id=str(turn_id))

    from services.coach.app.db.tables import turn_scores as turn_scores_table

    result = await db_session.execute(
        select(turn_scores_table).where(turn_scores_table.c.session_id == session_id)
    )
    rows = result.mappings().all()
    # delivery + 7 general_interview criteria, per turn, for 3 turns
    assert len(rows) == 3 * 8

    await generate_report({"redis": None}, session_id=str(session_id))

    from services.coach.app.db.tables import reports as reports_table
    from services.coach.app.db.tables import session_scores as session_scores_table

    report_result = await db_session.execute(
        select(reports_table).where(reports_table.c.session_id == session_id)
    )
    report_row = report_result.mappings().first()
    assert report_row is not None
    assert report_row["status"] == "ready"
    assert report_row["summary"] == "fake summary"
    assert report_row["low_sample_size"] is False

    score_result = await db_session.execute(
        select(session_scores_table).where(session_scores_table.c.session_id == session_id)
    )
    score_rows = score_result.mappings().all()
    assert len(score_rows) == 8  # 7 rubric criteria + delivery
    delivery_row = next(r for r in score_rows if r["criterion_key"] == "delivery")
    assert delivery_row["aggregate_score"] is not None


@pytest.mark.asyncio
async def test_score_turn_run_twice_produces_one_row_not_two(
    db_session: AsyncSession, seeded_content: dict[str, dict[str, object]]
) -> None:
    """Task 2.2d's own acceptance criterion, run against the real DB constraint that makes it
    true — the `uq_turn_scores_turn_criterion` UniqueConstraint from Phase 0."""
    from services.coach.app.report.build import score_turn

    rubric_ids = seeded_content["rubric_ids"]
    rubric_id = rubric_ids["general_interview"]
    session_id, _user_id, turn_ids = await _seed_session_with_turns(
        db_session, rubric_id=rubric_id, rubric_slug="general_interview", n_user_turns=1
    )
    await db_session.commit()
    turn_id = turn_ids[0]

    await score_turn({}, session_id=str(session_id), turn_id=str(turn_id))
    await score_turn({}, session_id=str(session_id), turn_id=str(turn_id))

    from services.coach.app.db.tables import turn_scores as turn_scores_table

    result = await db_session.execute(
        select(turn_scores_table).where(
            turn_scores_table.c.turn_id == turn_id,
            turn_scores_table.c.criterion_key == "delivery",
        )
    )
    rows = result.mappings().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_low_sample_size_flagged_on_a_two_turn_session(
    db_session: AsyncSession, seeded_content: dict[str, dict[str, object]]
) -> None:
    """Task 2.5's own example: "Session has 2 turns -> report generates but flags low sample
    size explicitly." """
    from services.coach.app.report.build import generate_report, score_turn

    rubric_ids = seeded_content["rubric_ids"]
    rubric_id = rubric_ids["general_interview"]
    session_id, _user_id, turn_ids = await _seed_session_with_turns(
        db_session, rubric_id=rubric_id, rubric_slug="general_interview", n_user_turns=2
    )
    await db_session.commit()

    for turn_id in turn_ids:
        await score_turn({}, session_id=str(session_id), turn_id=str(turn_id))
    await generate_report({"redis": None}, session_id=str(session_id))

    from services.coach.app.db.tables import reports as reports_table

    report_result = await db_session.execute(
        select(reports_table).where(reports_table.c.session_id == session_id)
    )
    report_row = report_result.mappings().first()
    assert report_row is not None
    assert report_row["low_sample_size"] is True
