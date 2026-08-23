"""docs/phase-4-BUILD.md's backend surface: onboarding, privacy settings + training-consent
revocation cascade, BYOK provider credentials, per-session consent, and the dashboard/progress
recommendation + trend logic. Real Postgres via testcontainers, same convention as
test_phase3_report_replay.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.core.config import get_settings
from services.api.app.core.security import create_access_token
from services.api.app.models import (
    Consent,
    Persona,
    Rubric,
    RubricCriterion,
    Scenario,
    SessionScore,
    Turn,
    User,
)
from services.api.app.models import Session as SessionModel

_has_groq_key = bool(os.environ.get("GROQ_API_KEY")) or bool(
    getattr(get_settings(), "groq_api_key", "")
)


async def _make_user(db_session: AsyncSession, email: str, **fields: object) -> User:
    user = User(email=email, **fields)  # type: ignore[arg-type]
    db_session.add(user)
    await db_session.flush()
    return user


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


async def _make_rubric(db_session: AsyncSession, *, criteria: list[str]) -> Rubric:
    rubric = Rubric(slug=f"r-{uuid.uuid4()}", name="Test rubric", description="d")
    db_session.add(rubric)
    await db_session.flush()
    for i, key in enumerate(criteria):
        db_session.add(
            RubricCriterion(
                rubric_id=rubric.id,
                key=key,
                name=key.replace("_", " ").title(),
                description="d",
                display_order=i,
                anchor_descriptors={"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"},
            )
        )
    await db_session.flush()
    return rubric


async def _make_persona(
    db_session: AsyncSession, *, voice_id: str = "en_US-lessac-medium"
) -> Persona:
    persona = Persona(
        slug=f"p-{uuid.uuid4()}",
        name="Test Persona",
        archetype="interviewer",
        temperament="neutral",
        voice_id=voice_id,
        brief="A test persona brief used only by this integration test.",
    )
    db_session.add(persona)
    await db_session.flush()
    return persona


async def _make_scenario(
    db_session: AsyncSession, *, family: str, difficulty: str, rubric: Rubric | None = None
) -> Scenario:
    persona = Persona(
        slug=f"p-{uuid.uuid4()}",
        name="Test Persona",
        archetype="interviewer",
        temperament="neutral",
        voice_id="en_US-lessac-medium",
        brief="A test persona brief used only by this integration test.",
    )
    db_session.add(persona)
    await db_session.flush()
    scenario = Scenario(
        slug=f"s-{uuid.uuid4()}",
        family=family,
        difficulty=difficulty,
        title=f"{family.title()} scenario ({difficulty})",
        brief="x" * 210,
        opening_strategy="Open.",
        difficulty_params={difficulty: {}},
        persona_id=persona.id,
        rubric_id=rubric.id if rubric else None,
    )
    db_session.add(scenario)
    await db_session.flush()
    return scenario


async def _make_closed_session(
    db_session: AsyncSession,
    *,
    user: User,
    scenario: Scenario,
    rubric: Rubric | None,
    created_at: datetime,
    scores: dict[str, float] | None = None,
    report_ready: bool = False,
    report_viewed: bool = False,
) -> SessionModel:
    session = SessionModel(
        user_id=user.id,
        scenario_id=scenario.id,
        status="closed",
        target_minutes=10,
        focus_areas=[],
        brief={
            "rubric_id": str(rubric.id) if rubric else None,
            "scenario_family": scenario.family,
            "scenario_title": scenario.title,
            "opening_strategy": scenario.opening_strategy,
        },
        duration_ms=10 * 60_000,
    )
    db_session.add(session)
    await db_session.flush()
    # created_at has a server_default — overwrite it directly after insert, matching how other
    # tests in this suite backdate rows for ordering (server_default only fires on INSERT).
    await db_session.execute(
        SessionModel.__table__.update()
        .where(SessionModel.id == session.id)
        .values(created_at=created_at)
    )
    await db_session.flush()
    session.created_at = created_at  # keep the in-memory object consistent with the DB

    for criterion_key, score in (scores or {}).items():
        db_session.add(
            SessionScore(
                session_id=session.id,
                criterion_key=criterion_key,
                aggregate_score=score,
                confidence=0.9,
                evidence_turn_ids=[],
                model_version="fake:1.0.0",
            )
        )
    if report_ready:
        from services.api.app.models import Report

        db_session.add(
            Report(
                session_id=session.id,
                status="ready",
                summary="s",
                strengths=["a"],
                growth_areas=["b"],
                generated_at=created_at,
            )
        )
        if report_viewed:
            session.report_viewed_at = created_at
    await db_session.flush()
    return session


class TestOnboarding:
    async def test_profile_patch_sets_goal_and_experience_level(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "onboard1@example.com")
        await db_session.commit()

        resp = await app_client.patch(
            "/me/profile",
            headers=_auth_headers(user),
            json={"goal": "technical_interview", "experience_level": "mid_level"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["goal"] == "technical_interview"
        assert resp.json()["experience_level"] == "mid_level"

    async def test_onboarding_complete_is_idempotent(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "onboard2@example.com")
        await db_session.commit()

        first = await app_client.post("/me/onboarding/complete", headers=_auth_headers(user))
        assert first.status_code == 200, first.text
        first_timestamp = first.json()["onboarded_at"]
        assert first_timestamp is not None

        second = await app_client.post("/me/onboarding/complete", headers=_auth_headers(user))
        assert second.json()["onboarded_at"] == first_timestamp


class TestPrivacySettingsAndConsentRevocation:
    async def test_defaults_are_no_training_consent_and_30_day_retention(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "privacy1@example.com")
        await db_session.commit()
        resp = await app_client.get("/me/privacy", headers=_auth_headers(user))
        assert resp.status_code == 200
        assert resp.json() == {"training_consent": False, "audio_retention_days": 30}

    async def test_revoking_training_consent_excludes_the_users_turns(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "privacy2@example.com", training_consent=True)
        scenario = await _make_scenario(db_session, family="technical", difficulty="standard")
        session = await _make_closed_session(
            db_session,
            user=user,
            scenario=scenario,
            rubric=None,
            created_at=datetime.now(UTC),
        )
        db_session.add(
            Consent(
                session_id=session.id,
                recording_consent=True,
                training_consent=True,
                consent_version="test-v1",
            )
        )
        user_turn = Turn(
            session_id=session.id,
            index=0,
            speaker="user",
            text="My answer.",
            start_ms=0,
            end_ms=100,
            word_timings=[],
            truncated=False,
        )
        persona_turn = Turn(
            session_id=session.id,
            index=-1,
            speaker="persona",
            text="A question.",
            start_ms=0,
            end_ms=100,
            word_timings=[],
            truncated=False,
        )
        db_session.add_all([user_turn, persona_turn])
        await db_session.commit()

        resp = await app_client.patch(
            "/me/privacy", headers=_auth_headers(user), json={"training_consent": False}
        )
        assert resp.status_code == 200
        assert resp.json()["training_consent"] is False

        await db_session.refresh(user_turn)
        await db_session.refresh(persona_turn)
        assert user_turn.training_excluded is True
        # Only the user's own turns are excluded — a persona turn is synthetic, not the user's
        # contribution (services/user_service.py::revoke_training_consent's own docstring).
        assert persona_turn.training_excluded is False

    async def test_re_granting_consent_does_not_retroactively_un_exclude_turns(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "privacy3@example.com", training_consent=True)
        scenario = await _make_scenario(db_session, family="technical", difficulty="standard")
        session = await _make_closed_session(
            db_session, user=user, scenario=scenario, rubric=None, created_at=datetime.now(UTC)
        )
        db_session.add(
            Consent(
                session_id=session.id,
                recording_consent=True,
                training_consent=True,
                consent_version="test-v1",
            )
        )
        user_turn = Turn(
            session_id=session.id,
            index=0,
            speaker="user",
            text="My answer.",
            start_ms=0,
            end_ms=100,
            word_timings=[],
            truncated=False,
        )
        db_session.add(user_turn)
        await db_session.commit()

        await app_client.patch(
            "/me/privacy", headers=_auth_headers(user), json={"training_consent": False}
        )
        await app_client.patch(
            "/me/privacy", headers=_auth_headers(user), json={"training_consent": True}
        )

        await db_session.refresh(user_turn)
        assert user_turn.training_excluded is True  # a past revocation stays permanent


class TestProviderCredentials:
    async def test_no_credential_saved_yet_reports_a_clear_failure(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "byok1@example.com")
        await db_session.commit()
        resp = await app_client.post("/me/providers/groq/test", headers=_auth_headers(user))
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "no api key" in body["message"].lower()

    async def test_save_then_list_never_exposes_the_raw_key(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "byok2@example.com")
        await db_session.commit()

        put_resp = await app_client.put(
            "/me/providers/groq", headers=_auth_headers(user), json={"api_key": "gsk_fake_key"}
        )
        assert put_resp.status_code == 201, put_resp.text
        assert "api_key" not in put_resp.text
        assert "gsk_fake_key" not in put_resp.text
        assert put_resp.json()["has_key"] is True
        assert put_resp.json()["last_test_status"] == "untested"

        list_resp = await app_client.get("/me/providers", headers=_auth_headers(user))
        assert len(list_resp.json()) == 1
        assert "gsk_fake_key" not in list_resp.text

    async def test_delete_removes_the_credential(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "byok3@example.com")
        await db_session.commit()
        await app_client.put(
            "/me/providers/groq", headers=_auth_headers(user), json={"api_key": "gsk_fake_key"}
        )
        delete_resp = await app_client.delete("/me/providers/groq", headers=_auth_headers(user))
        assert delete_resp.status_code == 204
        list_resp = await app_client.get("/me/providers", headers=_auth_headers(user))
        assert list_resp.json() == []

    @pytest.mark.skipif(not _has_groq_key, reason="no GROQ_API_KEY configured")
    async def test_an_invalid_key_fails_the_live_connection_test(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A real call against the real Groq API (no mocking the thing under test, CLAUDE.md
        §7) with a syntactically-plausible but definitely-invalid key — deterministic: Groq
        will reject it with 401 regardless of which real account is configured."""
        user = await _make_user(db_session, "byok4@example.com")
        await db_session.commit()
        await app_client.put(
            "/me/providers/groq",
            headers=_auth_headers(user),
            json={"api_key": "gsk_definitely_invalid_test_key_0000000000000000000000"},
        )
        resp = await app_client.post("/me/providers/groq/test", headers=_auth_headers(user))
        assert resp.status_code == 200
        assert resp.json()["success"] is False


class TestConsentOnSessionCreate:
    async def test_ordinary_session_falls_back_to_the_users_account_default(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "consent1@example.com", training_consent=True)
        scenario = await _make_scenario(db_session, family="technical", difficulty="standard")
        await db_session.commit()

        resp = await app_client.post(
            "/sessions",
            headers=_auth_headers(user),
            json={"scenario_id": str(scenario.id), "difficulty": "standard", "target_minutes": 10},
        )
        assert resp.status_code == 201, resp.text
        session_id = resp.json()["id"]

        consent_result = await db_session.execute(
            select(Consent).where(Consent.session_id == uuid.UUID(session_id))
        )
        consent = consent_result.scalar_one()
        assert consent.recording_consent is True
        assert consent.training_consent is True  # inherited from the account default

    async def test_recruited_flow_can_explicitly_override_the_default(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "consent2@example.com", training_consent=True)
        scenario = await _make_scenario(db_session, family="technical", difficulty="standard")
        await db_session.commit()

        resp = await app_client.post(
            "/sessions",
            headers=_auth_headers(user),
            json={
                "scenario_id": str(scenario.id),
                "difficulty": "standard",
                "target_minutes": 10,
                "recording_consent": True,
                "training_consent": False,
            },
        )
        assert resp.status_code == 201, resp.text
        consent_result = await db_session.execute(
            select(Consent).where(Consent.session_id == uuid.UUID(resp.json()["id"]))
        )
        consent = consent_result.scalar_one()
        assert consent.training_consent is False  # explicit decline wins over the account default


class TestDashboardRecommendation:
    async def test_an_incomplete_session_is_recommended_for_continuation(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "dash1@example.com")
        scenario = await _make_scenario(db_session, family="technical", difficulty="standard")
        incomplete = SessionModel(
            user_id=user.id,
            scenario_id=scenario.id,
            status="active",
            target_minutes=10,
            focus_areas=[],
            brief={"scenario_family": "technical", "scenario_title": scenario.title},
        )
        db_session.add(incomplete)
        await db_session.commit()

        resp = await app_client.get("/me/dashboard", headers=_auth_headers(user))
        assert resp.status_code == 200, resp.text
        rec = resp.json()["recommendation"]
        assert rec["kind"] == "continue_session"
        assert rec["session_id"] == str(incomplete.id)

    async def test_a_never_attempted_family_is_recommended_over_the_fallback(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "dash2@example.com")
        await _make_scenario(db_session, family="technical", difficulty="standard")
        await _make_scenario(db_session, family="negotiation", difficulty="standard")
        await db_session.commit()

        resp = await app_client.get("/me/dashboard", headers=_auth_headers(user))
        rec = resp.json()["recommendation"]
        assert rec["kind"] == "start_scenario"
        assert "haven't tried" in rec["reason"]

    async def test_attention_panel_surfaces_an_unread_report(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "dash3@example.com")
        rubric = await _make_rubric(db_session, criteria=["structure"])
        scenario = await _make_scenario(
            db_session, family="technical", difficulty="standard", rubric=rubric
        )
        await _make_closed_session(
            db_session,
            user=user,
            scenario=scenario,
            rubric=rubric,
            created_at=datetime.now(UTC),
            scores={"structure": 4.0},
            report_ready=True,
            report_viewed=False,
        )
        await db_session.commit()

        resp = await app_client.get("/me/dashboard", headers=_auth_headers(user))
        attention = resp.json()["attention"]
        assert attention is not None
        assert attention["kind"] == "unread_report"

    async def test_attention_panel_is_absent_when_nothing_qualifies(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "dash4@example.com")
        await db_session.commit()
        resp = await app_client.get("/me/dashboard", headers=_auth_headers(user))
        assert resp.json()["attention"] is None


class TestProgressWeakestDimensionUsesTrendNotAbsolute:
    async def test_a_declining_high_scorer_beats_a_stable_lower_scorer(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Task 4.4's own worked example: "A criterion at 5 and declining is more urgent than
        one at 4 and stable." Fixture data where trend and absolute level disagree, exactly as
        the acceptance criterion asks for."""
        user = await _make_user(db_session, "progress1@example.com")
        rubric = await _make_rubric(db_session, criteria=["structure", "clarity"])
        scenario = await _make_scenario(
            db_session, family="technical", difficulty="standard", rubric=rubric
        )
        now = datetime.now(UTC)
        # "structure" declines from 5 to 3; "clarity" stays flat at 4 the whole time.
        for i, (structure_score, clarity_score) in enumerate([(5.0, 4.0), (4.0, 4.0), (3.0, 4.0)]):
            await _make_closed_session(
                db_session,
                user=user,
                scenario=scenario,
                rubric=rubric,
                created_at=now - timedelta(days=10 - i),
                scores={"structure": structure_score, "clarity": clarity_score},
            )
        await db_session.commit()

        resp = await app_client.get(
            "/me/progress", headers=_auth_headers(user), params={"family": "technical"}
        )
        assert resp.status_code == 200, resp.text
        weakest = resp.json()["weakest_dimension"]
        assert weakest is not None
        assert weakest["criterion_key"] == "structure"
        assert weakest["trend"] < 0

    async def test_family_defaults_to_the_most_practised_one_not_all(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "progress2@example.com")
        rubric = await _make_rubric(db_session, criteria=["structure"])
        tech = await _make_scenario(
            db_session, family="technical", difficulty="standard", rubric=rubric
        )
        neg = await _make_scenario(
            db_session, family="negotiation", difficulty="standard", rubric=rubric
        )
        now = datetime.now(UTC)
        await _make_closed_session(
            db_session, user=user, scenario=tech, rubric=rubric, created_at=now, scores={}
        )
        await _make_closed_session(
            db_session,
            user=user,
            scenario=tech,
            rubric=rubric,
            created_at=now - timedelta(days=1),
            scores={},
        )
        await _make_closed_session(
            db_session,
            user=user,
            scenario=neg,
            rubric=rubric,
            created_at=now - timedelta(days=2),
            scores={},
        )
        await db_session.commit()

        resp = await app_client.get("/me/progress", headers=_auth_headers(user))
        assert resp.json()["family"] == "technical"  # attempted twice, vs. negotiation once


class TestScenarioProgress:
    async def test_best_score_reflects_the_highest_of_multiple_attempts(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "scenprog1@example.com")
        rubric = await _make_rubric(db_session, criteria=["structure"])
        scenario = await _make_scenario(
            db_session, family="technical", difficulty="standard", rubric=rubric
        )
        now = datetime.now(UTC)
        await _make_closed_session(
            db_session,
            user=user,
            scenario=scenario,
            rubric=rubric,
            created_at=now - timedelta(days=2),
            scores={"structure": 3.0},
        )
        await _make_closed_session(
            db_session,
            user=user,
            scenario=scenario,
            rubric=rubric,
            created_at=now,
            scores={"structure": 5.0},
        )
        await db_session.commit()

        resp = await app_client.get("/me/scenario-progress", headers=_auth_headers(user))
        assert resp.status_code == 200, resp.text
        progress = resp.json()[str(scenario.id)]
        assert progress["attempts"] == 2
        assert progress["best_score"] == 5.0


class TestExport:
    async def test_export_includes_profile_and_sessions_but_never_api_keys(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "export1@example.com")
        scenario = await _make_scenario(db_session, family="technical", difficulty="standard")
        await _make_closed_session(
            db_session, user=user, scenario=scenario, rubric=None, created_at=datetime.now(UTC)
        )
        await db_session.commit()
        await app_client.put(
            "/me/providers/groq", headers=_auth_headers(user), json={"api_key": "gsk_fake_key"}
        )

        resp = await app_client.get("/me/export", headers=_auth_headers(user))
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["sessions"]) == 1
        assert "gsk_fake_key" not in resp.text


class TestVoicePreviewToken:
    async def test_mints_a_token_scoped_to_the_personas_voice(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from services.realtime.app.core.exceptions import AuthInvalidTokenError
        from services.realtime.app.core.security import validate_voice_preview_token

        user = await _make_user(db_session, "voicepreview1@example.com")
        persona = await _make_persona(db_session, voice_id="en_US-ryan-high")
        await db_session.commit()

        resp = await app_client.post(
            f"/personas/{persona.id}/voice-preview-token", headers=_auth_headers(user)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["voice_id"] == "en_US-ryan-high"

        claims = validate_voice_preview_token(body["token"], expected_voice_id="en_US-ryan-high")
        assert claims.user_id == str(user.id)

        # Not single-use — a library page may reasonably let someone replay the sample.
        again = validate_voice_preview_token(body["token"], expected_voice_id="en_US-ryan-high")
        assert again.user_id == str(user.id)

        # Scoped to the exact voice — can't be replayed against a different one.
        with pytest.raises(AuthInvalidTokenError):
            validate_voice_preview_token(body["token"], expected_voice_id="en_US-lessac-medium")

    async def test_404s_for_a_nonexistent_persona(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "voicepreview2@example.com")
        await db_session.commit()
        resp = await app_client.post(
            f"/personas/{uuid.uuid4()}/voice-preview-token", headers=_auth_headers(user)
        )
        assert resp.status_code == 404
