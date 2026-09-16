"""NOT REAL DATA. Placeholder sessions/turns/consents so the rest of the Phase 5 pipeline
(annotation queue, training smoke-test, eval harness) has enough rows to exercise end-to-end in
an environment with no real recruited participants (Phase 4's Day 17 was never run — see
docs/PHASE5-WALKTHROUGH.md) and, at most, a handful of real self-testing sessions.

Every row this writes is tagged unmistakably:
  - user emails end in `@phase5-dev-fixture.invalid` (a reserved, non-routable TLD per RFC 2606)
  - every session's `brief` carries `{"dev_fixture": true}`
  - `dataset_revisions.notes` gets an explicit warning whenever a build included these rows
    (see build.py)

Idempotent: reruns delete and re-insert the same fixed set (`FIXTURE_MARKER` speakers), never
accumulate duplicates. This is the training-data equivalent of Phase 0/1's synthetic Piper audio
fixtures used because no microphone existed — never claimed as real, never present in any
`docs/RESULTS.md` number.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.models import Consent, Scenario, Turn, User  # noqa: E402
from app.models import Session as SessionModel
from app.models.base import uuid7  # noqa: E402
from app.models.consent import CURRENT_CONSENT_VERSION  # noqa: E402

FIXTURE_EMAIL_DOMAIN = "phase5-dev-fixture.invalid"
N_FIXTURE_SPEAKERS = 9  # >= 8, to clear Task 5.2's own speaker-count target in a smoke test

# Hand-written answers spanning the quality scale (1-5), reused round-robin across fixture
# speakers/sessions so every quality tier and every criterion score point appears at least
# once — the point is to exercise stratification and the ablation ladder's *code paths*, not
# to resemble a real distribution of real interview answers.
_SAMPLE_ANSWERS = [
    "Um, I don't really know, I guess I just did what they told me to do at the time.",
    (
        "So basically we had a problem and I fixed it. It was fine. I don't remember the "
        "details exactly but it worked out okay in the end I think."
    ),
    (
        "We had a service that kept timing out under load. I looked at the logs, found the "
        "slow query, and added an index. That helped some of it but there was still an issue "
        "with the connection pool that took a while to track down."
    ),
    (
        "The checkout service was failing about 4% of requests during peak traffic. I profiled "
        "it and found a synchronous call to a pricing API blocking the event loop. I moved it "
        "behind a cache with a five minute TTL, which dropped the failure rate to under 0.1%."
    ),
    (
        "Our checkout error rate hit 4.2% during Black Friday peak load. I traced it to a "
        "synchronous pricing-API call blocking the event loop for 800ms per request. I added a "
        "five-minute TTL cache in front of it and a circuit breaker for the cold-cache case, "
        "which cut the failure rate to 0.08% and p95 latency from 1.2s to 340ms."
    ),
]


async def seed_dev_fixtures(db: AsyncSession) -> None:
    await _delete_existing_fixtures(db)

    scenario_result = await db.execute(select(Scenario.id).limit(1))
    scenario_id = scenario_result.scalar_one_or_none()
    if scenario_id is None:
        print(
            "WARNING: no scenarios in the database - run `make seed` before --dev-fixtures.",
            file=sys.stderr,
        )
        return

    for i in range(N_FIXTURE_SPEAKERS):
        user = User(
            email=f"fixture-speaker-{i}@{FIXTURE_EMAIL_DOMAIN}",
            email_verified=True,
            name=f"Dev fixture speaker {i}",
            is_active=True,
            training_consent=True,
        )
        db.add(user)
        await db.flush()

        for j in range(3):  # 3 sessions per fixture speaker = 27 sessions, ~27 turns
            answer = _SAMPLE_ANSWERS[(i + j) % len(_SAMPLE_ANSWERS)]
            session = SessionModel(
                id=uuid7(),
                user_id=user.id,
                scenario_id=scenario_id,
                status="closed",
                end_reason="persona_concluded",
                target_minutes=5,
                brief={"dev_fixture": True},
                duration_ms=60_000,
            )
            db.add(session)
            await db.flush()

            db.add(
                Turn(
                    id=uuid7(),
                    session_id=session.id,
                    index=0,
                    speaker="persona",
                    text="Tell me about a time you fixed a difficult production issue.",
                    start_ms=0,
                    end_ms=0,
                )
            )
            db.add(
                Turn(
                    id=uuid7(),
                    session_id=session.id,
                    index=1,
                    speaker="user",
                    text=answer,
                    start_ms=0,
                    end_ms=60_000,
                )
            )
            db.add(
                Consent(
                    session_id=session.id,
                    recording_consent=False,
                    training_consent=True,
                    consent_version=CURRENT_CONSENT_VERSION,
                )
            )
    await db.flush()
    print(f"seeded {N_FIXTURE_SPEAKERS} dev-fixture speakers, 3 sessions each — NOT REAL DATA.")


async def _delete_existing_fixtures(db: AsyncSession) -> None:
    result = await db.execute(
        select(User.id).where(User.email.like(f"%@{FIXTURE_EMAIL_DOMAIN}"))
    )
    user_ids = [row[0] for row in result.all()]
    if not user_ids:
        return
    for user_id in user_ids:
        await db.execute(delete(User).where(User.id == user_id))
