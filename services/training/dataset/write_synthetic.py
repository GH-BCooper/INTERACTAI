"""Writes dataset/synthetic.py's generated (question, answer) pairs as real rows, reusing the
existing schema exactly as a real session would populate it — one Session (under a dedicated
system user, so `source` classification in build.py is a simple user_id check), two Turn rows
(the invented question as a `persona` turn, the generated answer as the `user` turn actually
scored), and a Consent row with `training_consent=true` (synthetic data was never anyone's real
speech, so there is nothing to protect — CLAUDE.md's privacy invariants are about real users).

Duration is *estimated* from word count at a plausible speaking rate, not measured — there is no
real audio for synthetic text (CLAUDE.md §2.8: never store persona audio; there is no audio here
to store on either side). This is disclosed in the written note on the session's brief, not
just this docstring, so a later reader of raw rows sees it too.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import get_training_settings  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.models import Consent, Scenario, Turn, User  # noqa: E402
from app.models import Session as SessionModel
from app.models.base import uuid7  # noqa: E402
from app.models.consent import CURRENT_CONSENT_VERSION  # noqa: E402

ESTIMATED_WORDS_PER_MINUTE = 140  # a plausible spoken-interview pace; documented as estimated


async def _get_or_create_synthetic_user(db: AsyncSession) -> object:
    settings = get_training_settings()
    result = await db.execute(select(User).where(User.email == settings.synthetic_user_email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user.id
    user = User(
        email=settings.synthetic_user_email,
        email_verified=True,
        name="Synthetic data (Phase 5)",
        is_active=True,
        training_consent=True,
    )
    db.add(user)
    await db.flush()
    return user.id


async def write_synthetic_turns(db: AsyncSession, generated: list[dict[str, object]]) -> list[str]:
    """Returns the new user-turn ids written. One Session + two Turn rows + one Consent row per
    generated item, matching the shape build.py's eligibility query expects (Consent row with
    training_consent=true, Turn.speaker in {persona, user})."""
    synthetic_user_id = await _get_or_create_synthetic_user(db)
    new_turn_ids: list[str] = []

    for item in generated:
        scenario_id = item["scenario_id"]
        question = str(item["question"])
        answer = str(item["answer"])
        quality_level = int(item["quality_level"])

        scenario_result = await db.execute(select(Scenario.id).where(Scenario.id == scenario_id))
        if scenario_result.scalar_one_or_none() is None:
            continue  # scenario removed between query and write; skip rather than FK-violate

        word_count = max(1, len(answer.split()))
        duration_ms = int((word_count / ESTIMATED_WORDS_PER_MINUTE) * 60_000)

        session = SessionModel(
            id=uuid7(),
            user_id=synthetic_user_id,
            scenario_id=scenario_id,
            status="closed",
            end_reason="persona_concluded",
            target_minutes=5,
            brief={
                "synthetic": True,
                "quality_level": quality_level,
                "note": "Phase 5 TASK 5.2b synthetic generation - duration is estimated from "
                "word count, not measured audio.",
            },
            duration_ms=duration_ms,
        )
        db.add(session)
        await db.flush()

        persona_turn = Turn(
            id=uuid7(),
            session_id=session.id,
            index=0,
            speaker="persona",
            text=question,
            start_ms=0,
            end_ms=0,
        )
        user_turn = Turn(
            id=uuid7(),
            session_id=session.id,
            index=1,
            speaker="user",
            text=answer,
            start_ms=0,
            end_ms=duration_ms,
        )
        db.add(persona_turn)
        db.add(user_turn)

        consent = Consent(
            session_id=session.id,
            recording_consent=False,
            training_consent=True,
            consent_version=CURRENT_CONSENT_VERSION,
        )
        db.add(consent)
        await db.flush()
        new_turn_ids.append(str(user_turn.id))

    return new_turn_ids
