"""docs/phase-5-BUILD.md TASK 5.3's admin-only annotation tool: /admin/annotate/*. Real Postgres
via testcontainers, same convention as test_phase4_dashboard_privacy_byok.py. Covers the
acceptance criteria that are actually testable at the API layer: admin-only gating, the response
shape never carries a model prediction, order/exclusion of already-labelled items, round
tracking, and the pre-label mismatch guard (Task 5.3d).
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.core.security import create_access_token
from services.api.app.models import (
    Consent,
    DatasetMember,
    DatasetRevision,
    Persona,
    Rubric,
    RubricCriterion,
    Scenario,
    Turn,
    User,
)
from services.api.app.models import Session as SessionModel
from services.api.app.models.consent import CURRENT_CONSENT_VERSION


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


async def _seed_labelable_turn(
    db_session: AsyncSession, *, split: str = "train", double_labeled: bool = False
) -> tuple[Turn, str]:
    persona = Persona(
        slug=f"p-{uuid.uuid4()}",
        name="Test Persona",
        archetype="interviewer",
        temperament="neutral",
        voice_id="en_US-lessac-medium",
        brief="Test persona brief.",
    )
    db_session.add(persona)
    await db_session.flush()

    rubric = Rubric(slug=f"r-{uuid.uuid4()}", name="Test rubric", description="d")
    db_session.add(rubric)
    await db_session.flush()
    db_session.add(
        RubricCriterion(
            rubric_id=rubric.id,
            key="structure",
            name="Structure",
            description="d",
            display_order=0,
            anchor_descriptors={"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"},
        )
    )
    await db_session.flush()

    scenario = Scenario(
        slug=f"s-{uuid.uuid4()}",
        family="technical",
        difficulty="standard",
        title="Test scenario",
        brief="x" * 200,
        opening_strategy="Tell me about a project.",
        difficulty_params={"gentle": {}, "standard": {}, "hard": {}},
        persona_id=persona.id,
        rubric_id=rubric.id,
    )
    db_session.add(scenario)
    await db_session.flush()

    speaker_user = User(email=f"speaker-{uuid.uuid4()}@example.com")
    db_session.add(speaker_user)
    await db_session.flush()

    session = SessionModel(
        user_id=speaker_user.id,
        scenario_id=scenario.id,
        status="closed",
        target_minutes=5,
        brief={},
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(
        Consent(
            session_id=session.id,
            recording_consent=True,
            training_consent=True,
            consent_version=CURRENT_CONSENT_VERSION,
        )
    )

    persona_turn = Turn(
        session_id=session.id, index=0, speaker="persona", text="Tell me about a project.",
        start_ms=0, end_ms=0,
    )
    user_turn = Turn(
        session_id=session.id, index=1, speaker="user", text="I built a caching layer.",
        start_ms=0, end_ms=5000,
    )
    db_session.add(persona_turn)
    db_session.add(user_turn)
    await db_session.flush()

    revision_hash = f"test-revision-{uuid.uuid4()}"
    db_session.add(
        DatasetRevision(
            hash=revision_hash,
            turn_count=1,
            label_count=0,
            speaker_count=1,
            source_breakdown={"self": 0, "recruited": 1, "synthetic": 0},
            split_counts={"train": 1 if split == "train" else 0},
            excluded_turn_ids=[],
        )
    )
    await db_session.flush()
    db_session.add(
        DatasetMember(
            dataset_revision_hash=revision_hash,
            turn_id=user_turn.id,
            session_id=session.id,
            speaker_key=str(speaker_user.id),
            split=split,
            source="recruited",
            double_labeled=double_labeled,
        )
    )
    await db_session.flush()
    return user_turn, revision_hash


class TestAdminGate:
    async def test_non_admin_is_forbidden(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = User(email=f"nonadmin-{uuid.uuid4()}@example.com", is_admin=False)
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()

        resp = await app_client.get("/admin/annotate/queue", headers=_auth_headers(user))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_admin_can_reach_the_queue(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = User(email=f"admin-{uuid.uuid4()}@example.com", is_admin=True)
        db_session.add(admin)
        await _seed_labelable_turn(db_session)
        await db_session.commit()

        resp = await app_client.get("/admin/annotate/queue", headers=_auth_headers(admin))
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestQueueContract:
    async def test_queue_item_never_carries_a_model_prediction_field(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """TASK 5.3a: "It must NEVER show the model's prediction." Verified structurally, not
        just by inspection — the only score-shaped field allowed is `pre_label_score`, and even
        that is null unless the caller explicitly opts into pre-labelling on a train-split item.
        """
        admin = User(email=f"admin-{uuid.uuid4()}@example.com", is_admin=True)
        db_session.add(admin)
        await _seed_labelable_turn(db_session, split="validation")
        await db_session.commit()

        resp = await app_client.get("/admin/annotate/queue", headers=_auth_headers(admin))
        item = resp.json()[0]
        assert set(item.keys()) == {
            "turn_id", "session_id", "question", "answer_text", "answer_is_scrubbed",
            "audio_url", "audio_start_ms", "audio_end_ms", "criterion_key", "criterion_name",
            "anchor_descriptors", "split", "double_labeled", "pre_label_score",
        }
        assert item["pre_label_score"] is None  # validation split: never pre-labelled

    async def test_full_anchor_descriptors_are_present(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = User(email=f"admin-{uuid.uuid4()}@example.com", is_admin=True)
        db_session.add(admin)
        await _seed_labelable_turn(db_session)
        await db_session.commit()

        resp = await app_client.get("/admin/annotate/queue", headers=_auth_headers(admin))
        anchors = resp.json()[0]["anchor_descriptors"]
        assert set(anchors.keys()) == {"1", "2", "3", "4", "5"}


class TestSubmissionAndProgress:
    async def test_submitting_removes_the_item_from_this_admins_queue(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = User(email=f"admin-{uuid.uuid4()}@example.com", is_admin=True)
        db_session.add(admin)
        turn, _ = await _seed_labelable_turn(db_session)
        await db_session.commit()

        submit_resp = await app_client.post(
            "/admin/annotate/submit",
            headers=_auth_headers(admin),
            json={"turn_id": str(turn.id), "criterion_key": "structure", "score": 4},
        )
        assert submit_resp.status_code == 201, submit_resp.text
        assert submit_resp.json()["round"] == 1

        queue_resp = await app_client.get("/admin/annotate/queue", headers=_auth_headers(admin))
        assert queue_resp.json() == []

    async def test_a_second_admin_can_independently_label_the_same_item(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin_one = User(email=f"admin1-{uuid.uuid4()}@example.com", is_admin=True)
        admin_two = User(email=f"admin2-{uuid.uuid4()}@example.com", is_admin=True)
        db_session.add(admin_one)
        db_session.add(admin_two)
        turn, _ = await _seed_labelable_turn(db_session, split="test", double_labeled=True)
        await db_session.commit()

        for admin, score in ((admin_one, 4), (admin_two, 2)):
            resp = await app_client.post(
                "/admin/annotate/submit",
                headers=_auth_headers(admin),
                json={"turn_id": str(turn.id), "criterion_key": "structure", "score": score},
            )
            assert resp.status_code == 201, resp.text

        progress_resp = await app_client.get(
            "/admin/annotate/progress", headers=_auth_headers(admin_one)
        )
        progress = progress_resp.json()
        assert progress["double_labeled_with_two_annotators"] == 1
        assert progress["disagreements_pending_adjudication"] == 1  # |4-2| > 1

    async def test_mismatched_pre_label_score_is_rejected(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = User(email=f"admin-{uuid.uuid4()}@example.com", is_admin=True)
        db_session.add(admin)
        turn, _ = await _seed_labelable_turn(db_session)
        await db_session.commit()

        resp = await app_client.post(
            "/admin/annotate/submit",
            headers=_auth_headers(admin),
            json={
                "turn_id": str(turn.id),
                "criterion_key": "structure",
                "score": 3,
                "pre_label_score": 5,  # no PreLabel row exists at all for this pair
            },
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_revisiting_the_same_pair_increments_round(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = User(email=f"admin-{uuid.uuid4()}@example.com", is_admin=True)
        db_session.add(admin)
        turn, _ = await _seed_labelable_turn(db_session)
        await db_session.commit()

        first = await app_client.post(
            "/admin/annotate/submit",
            headers=_auth_headers(admin),
            json={"turn_id": str(turn.id), "criterion_key": "structure", "score": 3},
        )
        second = await app_client.post(
            "/admin/annotate/submit",
            headers=_auth_headers(admin),
            json={"turn_id": str(turn.id), "criterion_key": "structure", "score": 4},
        )
        assert first.json()["round"] == 1
        assert second.json()["round"] == 2
