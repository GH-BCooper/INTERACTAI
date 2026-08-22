"""Phase 3's new backend surface (docs/phase-3-BUILD.md TASK 3.3/3.4): turns/scores/recording
for the report, annotations, retry-one-question, the replay-token handshake with realtime, and
the OAuth callback redirect fix (docs/decisions/0013) — everything the practice room/report UI
was built against. Real Postgres via testcontainers, same as every other integration test here;
`score_turn`/`generate_report` themselves (real model calls) are covered separately in
test_coach_pipeline.py, so these tests write `TurnScore`/`SessionScore`/`Report` rows directly to
exercise the read/write endpoints in isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.core.security import (
    REPLAY_TOKEN_TTL_SECONDS,
    create_access_token,
    mint_replay_token,
)
from services.api.app.models import (
    Annotation,
    Persona,
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
from services.api.app.models import Session as SessionModel


async def _make_user(db_session: AsyncSession, email: str) -> User:
    user = User(email=email)
    db_session.add(user)
    await db_session.flush()
    return user


async def _seed_session_with_rubric(
    db_session: AsyncSession, *, user: User
) -> tuple[SessionModel, uuid.UUID, str]:
    """One persona turn + one user turn, a one-criterion rubric, and a session whose frozen
    `brief` points at it — the minimum real shape every new endpoint under test needs."""
    persona = Persona(
        slug=f"p-{uuid.uuid4()}",
        name="Test Persona",
        archetype="interviewer",
        temperament="neutral",
        voice_id="en_US-lessac-medium",
        brief="A test persona brief used only by this integration test.",
    )
    rubric = Rubric(slug=f"r-{uuid.uuid4()}", name="Test rubric", description="d")
    db_session.add_all([persona, rubric])
    await db_session.flush()

    criterion = RubricCriterion(
        rubric_id=rubric.id,
        key="structure",
        name="Structure",
        description="d",
        display_order=0,
        anchor_descriptors={"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"},
    )
    db_session.add(criterion)
    await db_session.flush()

    scenario = Scenario(
        slug=f"s-{uuid.uuid4()}",
        family="technical",
        difficulty="standard",
        title="T",
        brief="x" * 210,
        opening_strategy="Open.",
        difficulty_params={"standard": {}},
        persona_id=persona.id,
        rubric_id=rubric.id,
    )
    db_session.add(scenario)
    await db_session.flush()

    session = SessionModel(
        user_id=user.id,
        scenario_id=scenario.id,
        status="closed",
        target_minutes=10,
        focus_areas=[],
        brief={"rubric_id": str(rubric.id), "opening_strategy": scenario.opening_strategy},
    )
    db_session.add(session)
    await db_session.flush()

    # index=-1 mirrors services/realtime/app/persona/opening.py's OPENING_TURN_INDEX — the
    # scripted opening line is the "question" behind the very first (index 0) user turn.
    # services/coach/app/report/build.py's _find_preceding_question (and
    # session_service.create_retry_session's reimplementation of it) both rely on this: the
    # preceding persona turn's index must be strictly less than the answering user turn's.
    base_time = datetime.now(UTC)
    persona_turn = Turn(
        session_id=session.id,
        created_at=base_time,
        index=-1,
        speaker="persona",
        text="Tell me about a time you pushed back on a decision?",
        start_ms=0,
        end_ms=100,
        word_timings=[],
        truncated=False,
    )
    db_session.add(persona_turn)
    await db_session.flush()

    user_turn = Turn(
        session_id=session.id,
        created_at=base_time + timedelta(milliseconds=5),
        index=0,
        speaker="user",
        text="I disagreed with the rollout plan and proposed a staged rollout instead.",
        start_ms=200,
        end_ms=900,
        word_timings=[{"word": "I", "start_ms": 200, "end_ms": 250}],
        truncated=False,
        asr_confidence=0.95,
    )
    db_session.add(user_turn)
    await db_session.flush()

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
    return session, user_turn.id, "structure"


class TestSessionTurns:
    async def test_turns_include_metrics_and_gated_scores(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "turns-owner@example.com")
        session, user_turn_id, criterion_key = await _seed_session_with_rubric(
            db_session, user=user
        )
        db_session.add(
            TurnScore(
                session_id=session.id,
                turn_id=user_turn_id,
                criterion_key=criterion_key,
                score=4,
                confidence=0.9,
                evidence_spans=[{"start": 0, "end": 10}],
                model_version="fake:1.0.0",
            )
        )
        db_session.add(
            TurnScore(
                session_id=session.id,
                turn_id=user_turn_id,
                criterion_key="delivery",
                score=None,  # gated below confidence threshold — CLAUDE.md §1.6
                confidence=0.1,
                evidence_spans=[],
                model_version="deterministic-v1",
            )
        )
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.get(
            f"/sessions/{session.id}/turns", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        turns = resp.json()
        assert len(turns) == 2
        assert turns[0]["speaker"] == "persona"
        assert turns[0]["metrics"] is None

        user_turn_out = turns[1]
        assert user_turn_out["speaker"] == "user"
        assert user_turn_out["metrics"]["wpm"] == 140.0
        scores_by_key = {s["criterion_key"]: s for s in user_turn_out["scores"]}
        assert scores_by_key["structure"]["score"] == 4
        assert scores_by_key["delivery"]["score"] is None  # never fabricated

    async def test_turns_endpoint_forbidden_for_non_owner(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        owner = await _make_user(db_session, "owner2@example.com")
        other = await _make_user(db_session, "other2@example.com")
        session, _turn_id, _key = await _seed_session_with_rubric(db_session, user=owner)
        await db_session.commit()

        token = create_access_token(str(other.id))
        resp = await app_client.get(
            f"/sessions/{session.id}/turns", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403


class TestSessionScores:
    async def test_scores_carry_rubric_anchor_text_and_a_synthetic_delivery_row(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "scores-owner@example.com")
        session, _turn_id, criterion_key = await _seed_session_with_rubric(db_session, user=user)
        db_session.add(
            SessionScore(
                session_id=session.id,
                criterion_key=criterion_key,
                aggregate_score=4.0,
                confidence=0.9,
                evidence_turn_ids=[],
                model_version="fake:1.0.0",
            )
        )
        db_session.add(
            SessionScore(
                session_id=session.id,
                criterion_key="delivery",
                aggregate_score=3.5,
                confidence=1.0,
                evidence_turn_ids=[],
                model_version="deterministic-v1",
            )
        )
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.get(
            f"/sessions/{session.id}/scores", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        rows = {r["criterion_key"]: r for r in resp.json()}

        assert rows[criterion_key]["name"] == "Structure"
        assert rows[criterion_key]["anchor_descriptors"]["4"] == "d"

        assert rows["delivery"]["name"] == "Delivery"
        assert set(rows["delivery"]["anchor_descriptors"].keys()) == {"1", "2", "3", "4", "5"}

        # Rubric criteria (display_order 0) sort ahead of the synthetic delivery row.
        keys_in_order = list(rows.keys())
        assert keys_in_order.index(criterion_key) < keys_in_order.index("delivery")


class TestSessionRecording:
    async def test_recording_absent_when_never_captured(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "no-recording@example.com")
        session, _turn_id, _key = await _seed_session_with_rubric(db_session, user=user)
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.get(
            f"/sessions/{session.id}/recording", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["url"] is None
        assert body["format"] is None

    async def test_recording_present_mints_a_presigned_url(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "has-recording@example.com")
        session, _turn_id, _key = await _seed_session_with_rubric(db_session, user=user)
        session.recording_key = f"users/{user.id}/sessions/{session.id}.opus"
        session.recording_format = "opus"
        session.peaks = [0.1, 0.2, 0.3]
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.get(
            f"/sessions/{session.id}/recording", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["url"] and body["url"].startswith("http")
        assert body["format"] == "opus"
        assert body["peaks"] == [0.1, 0.2, 0.3]


class TestReplayToken:
    async def test_minted_token_validates_against_realtimes_verifier(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from services.realtime.app.core.exceptions import AuthInvalidTokenError
        from services.realtime.app.core.security import validate_replay_token

        user = await _make_user(db_session, "replay@example.com")
        session, _turn_id, _key = await _seed_session_with_rubric(db_session, user=user)
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.post(
            f"/sessions/{session.id}/replay-token", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["expires_in"] == REPLAY_TOKEN_TTL_SECONDS

        claims = validate_replay_token(body["token"], expected_session_id=str(session.id))
        assert claims.user_id == str(user.id)

        with pytest.raises(AuthInvalidTokenError):
            validate_replay_token(body["token"], expected_session_id=str(uuid.uuid4()))

    async def test_replay_token_is_not_single_use(self) -> None:
        """Unlike the WS handshake token, scrubbing a replay makes many synthesis calls — the
        same token must keep validating (docs/decisions/0014)."""
        from services.realtime.app.core.security import validate_replay_token

        token = mint_replay_token("session-1", "user-1")
        first = validate_replay_token(token, expected_session_id="session-1")
        second = validate_replay_token(token, expected_session_id="session-1")
        assert first.user_id == second.user_id == "user-1"


class TestAnnotations:
    async def test_repeated_annotation_by_the_same_reviewer_increments_round(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "annotator@example.com")
        session, turn_id, criterion_key = await _seed_session_with_rubric(db_session, user=user)
        await db_session.commit()

        token = create_access_token(str(user.id))
        headers = {"Authorization": f"Bearer {token}"}
        body = {"turn_id": str(turn_id), "criterion_key": criterion_key, "score": 5}

        first = await app_client.post(
            f"/sessions/{session.id}/annotations", json=body, headers=headers
        )
        assert first.status_code == 201, first.text
        assert first.json()["round"] == 1

        second = await app_client.post(
            f"/sessions/{session.id}/annotations", json=body, headers=headers
        )
        assert second.status_code == 201, second.text
        assert second.json()["round"] == 2

        rows = (
            await db_session.execute(select(Annotation).where(Annotation.turn_id == turn_id))
        ).scalars().all()
        assert len(rows) == 2

    async def test_annotating_a_turn_from_another_session_is_rejected(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "annotator2@example.com")
        session_a, _turn_a, criterion_key = await _seed_session_with_rubric(db_session, user=user)
        _session_b, turn_b, _key_b = await _seed_session_with_rubric(db_session, user=user)
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.post(
            f"/sessions/{session_a.id}/annotations",
            json={"turn_id": str(turn_b), "criterion_key": criterion_key, "score": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


class TestRetryOneQuestion:
    async def test_retry_creates_a_short_linked_session_seeded_with_the_question(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "retry@example.com")
        session, user_turn_id, _key = await _seed_session_with_rubric(db_session, user=user)
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.post(
            f"/sessions/{session.id}/retry",
            json={"turn_id": str(user_turn_id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        retry_out = resp.json()
        assert retry_out["target_minutes"] == 5
        assert retry_out["retry_of_session_id"] == str(session.id)
        assert retry_out["retry_of_turn_id"] == str(user_turn_id)

        retry_row = await db_session.get(SessionModel, uuid.UUID(retry_out["id"]))
        assert retry_row is not None
        assert retry_row.brief["opening_strategy"] == (
            "Tell me about a time you pushed back on a decision?"
        )
        assert retry_row.scenario_id == session.scenario_id

    async def test_retry_on_a_persona_turn_is_rejected(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "retry2@example.com")
        session, _user_turn_id, _key = await _seed_session_with_rubric(db_session, user=user)
        persona_turn_result = await db_session.execute(
            select(Turn).where(Turn.session_id == session.id, Turn.speaker == "persona")
        )
        persona_turn = persona_turn_result.scalar_one()
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.post(
            f"/sessions/{session.id}/retry",
            json={"turn_id": str(persona_turn.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


class TestReportOut:
    async def test_report_endpoint_maps_next_actions_and_flags(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "report-out@example.com")
        session, turn_id, _key = await _seed_session_with_rubric(db_session, user=user)
        db_session.add(
            Report(
                session_id=session.id,
                status="ready",
                summary="A fake summary.",
                strengths=["clear structure"],
                growth_areas=["more specifics"],
                next_actions=[{"text": "Quantify the impact next time.", "turn_id": str(turn_id)}],
                highlight_turn_id=turn_id,
                lowlight_turn_id=None,
                low_sample_size=True,
                generated_at=datetime.now(UTC),
            )
        )
        await db_session.commit()

        token = create_access_token(str(user.id))
        resp = await app_client.get(
            f"/sessions/{session.id}/report", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["low_sample_size"] is True
        assert body["highlight_turn_id"] == str(turn_id)
        assert body["next_actions"] == [
            {"text": "Quantify the impact next time.", "turn_id": str(turn_id)}
        ]


class TestOAuthCallbackRedirect:
    async def test_callback_redirects_to_web_origin_with_token_fragment_and_sets_cookie(
        self, app_client: AsyncClient, redis_client: Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """docs/decisions/0013: the original Phase 0 handler returned JSON directly, which a
        browser landing here via a top-level OAuth redirect could never hand back to the SPA.

        Patches `app.routers.auth` (the bare-import module path `app_client`'s real running
        app was loaded through — see conftest.py's `API_DIR` sys.path insertion), not
        `services.api.app.routers.auth` — those are two distinct module objects even though
        they're the same file on disk, and only the former is the one FastAPI is actually
        dispatching requests through."""
        import app.routers.auth as auth_router
        from services.api.app.core.security import create_oauth_state
        from services.api.app.services.auth_service import OAuthUserInfo

        async def _fake_exchange(provider: str, *, code: str, redirect_uri: str) -> OAuthUserInfo:
            return OAuthUserInfo(
                provider_id="gh-123",
                email="oauth-user@example.com",
                email_verified=True,
                name="OAuth User",
                avatar_url=None,
            )

        monkeypatch.setattr(auth_router.auth_service, "exchange_code_for_user", _fake_exchange)

        # Reuse the real state-issuance path so this exercises the same CSRF check production does.
        # `redis_client` here is the exact same instance `app_client` was overridden to use
        # (conftest.py's `app_client` fixture depends on it) — pytest caches fixtures per test.
        state = await create_oauth_state(redis_client)

        resp = await app_client.get(
            "/auth/github/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
        assert resp.status_code == 307, resp.text
        location = resp.headers["location"]
        settings_web_origin = auth_router.get_settings().web_origin
        assert location.startswith(f"{settings_web_origin}/auth/callback#token=")
        assert "expires_in=" in location
        assert "interactai_refresh" in resp.headers.get("set-cookie", "")
