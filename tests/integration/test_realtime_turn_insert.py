"""Regression (found live in Phase 6): Phase 4's migration made `turns.training_excluded` NOT NULL
and then dropped its server default, but realtime's Core-table insert never sets it — every live
turn failed to persist with a NotNullViolation, the turn task died, and the persona never replied.
This drives realtime's own `insert_turn` against the real, migrated schema."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.models import Persona, Scenario, Turn, User
from services.api.app.models import Session as SessionModel
from services.realtime.app.db.repository import insert_turn


async def test_realtime_insert_turn_persists_against_migrated_schema(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"u-{uuid.uuid4()}@example.com")
    persona = Persona(
        slug=f"p-{uuid.uuid4()}",
        name="P",
        archetype="interviewer",
        temperament="neutral",
        voice_id="en_US-lessac-medium",
        brief="b",
    )
    db_session.add_all([user, persona])
    await db_session.flush()
    scenario = Scenario(
        slug=f"s-{uuid.uuid4()}",
        family="behavioural",
        difficulty="standard",
        title="T",
        brief="x" * 200,
        opening_strategy="o",
        difficulty_params={},
        persona_id=persona.id,
    )
    db_session.add(scenario)
    await db_session.flush()
    session = SessionModel(
        user_id=user.id, scenario_id=scenario.id, status="active", target_minutes=5, brief={}
    )
    db_session.add(session)
    await db_session.flush()

    turn_id = uuid.uuid4()
    await insert_turn(
        db_session,
        turn_id=turn_id,
        session_id=session.id,
        index=0,
        speaker="user",
        text="I added the index.",
        start_ms=0,
        end_ms=1500,
        word_timings=[],
        truncated=False,
        asr_confidence=0.9,
    )
    row = (await db_session.execute(select(Turn).where(Turn.id == turn_id))).scalar_one()
    assert row.training_excluded is False
