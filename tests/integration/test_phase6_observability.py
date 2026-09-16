"""Phase 6 TASK 6.1/6.2 — /admin/observability/* and /admin/evals/*, against real Postgres
(testcontainers). The 10,000 latency events here are synthetic load and live only inside this
test's rolled-back transaction — they never reach a database whose numbers are published.
"""

from __future__ import annotations

import random
import statistics
import time
import uuid

from httpx import AsyncClient
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.core.security import create_access_token
from services.api.app.models import (
    Annotation,
    LatencyEvent,
    ModelCall,
    Persona,
    Scenario,
    ShadowScore,
    Turn,
    TurnScore,
    User,
)
from services.api.app.models import Session as SessionModel
from services.api.app.models.observability import LATENCY_STAGES

N_TURNS = 1250  # x 8 stages = 10,000 latency events


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


async def _seed(db: AsyncSession) -> dict[str, object]:
    rng = random.Random(6)  # noqa: S311 — deterministic synthetic load, not security
    admin = User(email=f"admin-{uuid.uuid4()}@example.com", is_admin=True)
    speaker = User(email=f"speaker-{uuid.uuid4()}@example.com")
    persona = Persona(
        slug=f"p-{uuid.uuid4()}",
        name="P",
        archetype="interviewer",
        temperament="neutral",
        voice_id="en_US-lessac-medium",
        brief="b",
    )
    db.add_all([admin, speaker, persona])
    await db.flush()
    scenario = Scenario(
        slug=f"s-{uuid.uuid4()}",
        family="technical",
        difficulty="standard",
        title="T",
        brief="x" * 200,
        opening_strategy="o",
        difficulty_params={},
        persona_id=persona.id,
    )
    db.add(scenario)
    await db.flush()
    session = SessionModel(
        user_id=speaker.id, scenario_id=scenario.id, status="closed", target_minutes=5, brief={}
    )
    db.add(session)
    await db.flush()

    user_turn = Turn(
        session_id=session.id,
        index=1,
        speaker="user",
        text="I led the migration.",
        start_ms=1000,
        end_ms=4000,
    )
    persona_turn = Turn(
        session_id=session.id,
        index=2,
        speaker="persona",
        text="What broke first?",
        start_ms=5200,
        end_ms=6500,
    )
    db.add_all([user_turn, persona_turn])
    await db.flush()

    turn_ids = [user_turn.id] + [uuid.uuid4() for _ in range(N_TURNS - 1)]
    rows = []
    e2e_values = []
    for i, tid in enumerate(turn_ids):
        for stage in LATENCY_STAGES:
            d = rng.uniform(900, 1600) if stage == "e2e" else rng.uniform(10, 500)
            if stage == "e2e":
                e2e_values.append(d)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "session_id": session.id,
                    "turn_id": tid,
                    "stage": stage,
                    "duration_ms": d,
                    "host_class": "ci-cpu" if i % 2 else "dev-laptop-cpu",
                }
            )
    await db.execute(insert(LatencyEvent), rows)

    db.add_all(
        [
            ModelCall(
                session_id=session.id,
                turn_id=persona_turn.id,
                role="persona",
                model="groq/x",
                prompt_version="persona-static@1.0.0",
                tokens_in=900,
                tokens_out=40,
                ttft_ms=300,
                total_latency_ms=700,
                cost_cents=0.01,
                cached=True,
            ),
            ModelCall(
                session_id=session.id,
                turn_id=user_turn.id,
                role="judge",
                model="groq/x",
                prompt_version="scorer@1.0.0",
                tokens_in=2000,
                tokens_out=200,
                ttft_ms=None,
                total_latency_ms=1500,
                cost_cents=0.02,
                cached=False,
            ),
        ]
    )
    for key, model_score, labels in (("structure", 5, [2, 2]), ("clarity", 3, [3, 4])):
        db.add(
            TurnScore(
                session_id=session.id,
                turn_id=user_turn.id,
                criterion_key=key,
                score=model_score,
                confidence=0.9,
                evidence_spans=[],
                model_version="prompted@1",
            )
        )
        db.add(
            ShadowScore(
                session_id=session.id,
                turn_id=user_turn.id,
                criterion_key=key,
                score=model_score if key == "clarity" else 2,
                confidence=0.8,
                model_version="finetuned@1",
            )
        )
        for r, label in enumerate(labels, start=1):
            db.add(
                Annotation(
                    session_id=session.id,
                    turn_id=user_turn.id,
                    annotator_id=admin.id,
                    criterion_key=key,
                    round=r,
                    score=label,
                    pre_labelled=False,
                )
            )
    await db.flush()
    return {
        "admin": admin,
        "speaker": speaker,
        "session": session,
        "user_turn": user_turn,
        "e2e": e2e_values,
    }


async def test_observability_and_evals_end_to_end(
    db_session: AsyncSession, app_client: AsyncClient
) -> None:
    seed = await _seed(db_session)
    admin = seed["admin"]
    assert isinstance(admin, User)
    h = _auth(admin)

    started = time.perf_counter()
    latency = (await app_client.get("/admin/observability/latency?days=30", headers=h)).json()
    stages = (await app_client.get("/admin/observability/stages?days=30", headers=h)).json()
    turns = (await app_client.get("/admin/observability/turns", headers=h)).json()
    calls = (await app_client.get("/admin/observability/model-calls", headers=h)).json()
    cost = (await app_client.get("/admin/observability/cost", headers=h)).json()
    elapsed = time.perf_counter() - started
    # TASK 6.1: "Page loads in < 2 s over 10,000 latency events" — every data call the page makes.
    assert elapsed < 2.0, elapsed

    # Header is the e2e distribution itself, not a sum of stage percentiles.
    e2e = sorted(seed["e2e"])  # type: ignore[arg-type]
    assert latency["overall"]["n"] == N_TURNS
    assert abs(latency["overall"]["p50"] - statistics.median(e2e)) < 1e-6
    assert latency["overall"]["p95"] < 1600  # a stage sum would be ~1600 + 7*~255
    assert latency["target_p95_ms"] == 1400
    assert set(latency["host_classes"]) >= {"ci-cpu", "dev-laptop-cpu"}
    filtered = (
        await app_client.get("/admin/observability/latency?days=30&host_class=ci-cpu", headers=h)
    ).json()
    assert filtered["overall"]["n"] == N_TURNS // 2

    assert [s["stage"] for s in stages] == [s for s in LATENCY_STAGES if s != "e2e"]
    assert len(turns) == 50

    user_turn = seed["user_turn"]
    assert isinstance(user_turn, Turn)
    wf = (await app_client.get(f"/admin/observability/turns/{user_turn.id}", headers=h)).json()
    assert wf["user_text"] == "I led the migration."
    assert wf["persona_text"] == "What broke first?"
    assert wf["persona_voice_id"] == "en_US-lessac-medium"
    ttft = next(s for s in wf["stages"] if s["stage"] == "model_ttft")
    assert ttft["model_calls"][0]["cached"] is True

    assert calls["cache_hits"] == 1 and calls["cache_misses"] == 1
    only_cached = (
        await app_client.get("/admin/observability/model-calls?cached=true", headers=h)
    ).json()
    assert only_cached["total"] == 1 and only_cached["items"][0]["role"] == "persona"

    # 2 turn_scores x (2000 in * $5 + 200 out * $25)/1M = $0.03 = 3.0 cents; actual judge 0.02.
    assert abs(cost["counterfactual_cents"] - 3.0) < 1e-9
    assert abs(cost["ratio"] - 150.0) < 1e-6

    cases = (await app_client.get("/admin/evals/cases", headers=h)).json()["items"]
    assert [c["criterion_key"] for c in cases] == ["structure", "clarity"]  # biggest gap first
    assert cases[0]["disagreement"] == 3.0 and cases[0]["human_scores"] == [2, 2]

    cmp = (
        await app_client.get(
            "/admin/evals/compare?version_a=prompted@1&version_b=finetuned@1", headers=h
        )
    ).json()
    assert cmp["shared_cases"] == 2 and cmp["disagreements"] == 1
    assert cmp["items"][0]["disagrees"] is True

    speaker = seed["speaker"]
    assert isinstance(speaker, User)
    forbidden = await app_client.get("/admin/observability/latency", headers=_auth(speaker))
    assert forbidden.status_code == 403


async def test_e2e_query_can_use_covering_index(db_session: AsyncSession) -> None:
    await _seed(db_session)
    await db_session.execute(text("ANALYZE latency_events"))
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = (
        (
            await db_session.execute(
                text(
                    "EXPLAIN SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) "
                    "FROM latency_events "
                    "WHERE stage = 'e2e' AND created_at >= now() - interval '7d'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert any("ix_latency_events_stage_created_at_cover" in line for line in plan), plan
