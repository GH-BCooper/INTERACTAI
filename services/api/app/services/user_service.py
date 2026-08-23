"""No raw SQL in routers (CLAUDE.md §5) — repository functions live here."""

from __future__ import annotations

import uuid as std_uuid
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import decrypt_secret, encrypt_secret
from ..core.s3 import delete_prefix
from ..models import Consent, Profile, ProviderCredential, Session, Turn, User

logger = structlog.get_logger(__name__)

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
CONNECTION_TEST_MODEL = "llama-3.3-70b-versatile"
CONNECTION_TEST_TIMEOUT_SECONDS = 10.0


async def get_user_by_id(db: AsyncSession, user_id: std_uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_profile(db: AsyncSession, user_id: std_uuid.UUID) -> Profile | None:
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def find_or_link_or_create_oauth_user(
    db: AsyncSession,
    *,
    provider: str,
    provider_id: str,
    email: str,
    email_verified: bool,
    name: str | None,
    avatar_url: str | None,
) -> User:
    """provider is "github" or "google". A user who signs in with a second provider under the
    same email is linked to their existing account rather than duplicated — the setup guide
    notes the audience has both.
    """
    is_github = provider == "github"
    provider_column = User.github_id if is_github else User.google_id

    result = await db.execute(select(User).where(provider_column == provider_id))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        if is_github:
            user.github_id = provider_id
        else:
            user.google_id = provider_id
        if not user.email_verified and email_verified:
            user.email_verified = True
        await db.flush()
        return user

    user = User(
        email=email,
        email_verified=email_verified,
        name=name,
        avatar_url=avatar_url,
        github_id=provider_id if is_github else None,
        google_id=None if is_github else provider_id,
    )
    db.add(user)
    await db.flush()
    return user


async def update_profile(
    db: AsyncSession,
    user_id: std_uuid.UUID,
    *,
    resume_text: str | None = None,
    target_role: str | None = None,
    clear_resume: bool = False,
    goal: str | None = None,
    experience_level: str | None = None,
    focus_areas: list[str] | None = None,
    captions_default: bool | None = None,
    speaking_rate: float | None = None,
    noise_suppression: bool | None = None,
    echo_cancellation: bool | None = None,
) -> Profile:
    profile = await get_profile(db, user_id)
    if profile is None:
        profile = Profile(user_id=user_id)
        db.add(profile)

    if clear_resume:
        profile.resume_text = None
        profile.resume_updated_at = None
    elif resume_text is not None:
        profile.resume_text = resume_text
        profile.resume_updated_at = datetime.now(UTC)

    if target_role is not None:
        profile.target_role = target_role
    if goal is not None:
        profile.goal = goal
    if experience_level is not None:
        profile.experience_level = experience_level
    if focus_areas is not None:
        profile.focus_areas = focus_areas
    if captions_default is not None:
        profile.captions_default = captions_default
    if speaking_rate is not None:
        profile.speaking_rate = speaking_rate
    if noise_suppression is not None:
        profile.noise_suppression = noise_suppression
    if echo_cancellation is not None:
        profile.echo_cancellation = echo_cancellation

    await db.flush()
    return profile


async def complete_onboarding(db: AsyncSession, user_id: std_uuid.UUID) -> User:
    """Task 4.3's "user already onboarded -> redirect to /app" edge case reads this once, set
    permanently the first time onboarding's step 4 launches a session — never cleared."""
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found.")
    if user.onboarded_at is None:
        user.onboarded_at = datetime.now(UTC)
        await db.flush()
    return user


async def update_privacy_settings(
    db: AsyncSession,
    user_id: std_uuid.UUID,
    *,
    training_consent: bool | None,
    audio_retention_days: int | None,
) -> User:
    """AS-03/AS-04. Turning `training_consent` off cascades immediately (Task 4.5a) — turning
    it on again is *not* retroactive (it only changes the default new sessions get), since a
    past revocation must stay permanent once logged."""
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found.")

    was_revoked = training_consent is False and user.training_consent is True
    if training_consent is not None:
        user.training_consent = training_consent
    if audio_retention_days is not None:
        user.audio_retention_days = audio_retention_days
    await db.flush()

    if was_revoked:
        await revoke_training_consent(db, user_id)
    return user


async def revoke_training_consent(db: AsyncSession, user_id: std_uuid.UUID) -> int:
    """Task 4.5a: "Training consent revocation cascades: turns are flagged
    training_excluded = true and are filtered out of every dataset build... the exclusion must
    be logged." Only the user's own turns carry anything to exclude (a persona turn is
    synthetic, already-generated text, not the user's contribution) from sessions whose own
    Consent row actually recorded training_consent=true at creation time — a session that was
    never asked, or that explicitly declined, has nothing to revoke. Returns the number of
    turns newly excluded (0 is a legitimate, common result, not an error)."""
    session_ids_subquery = (
        select(Consent.session_id)
        .join(Session, Session.id == Consent.session_id)
        .where(Session.user_id == user_id, Consent.training_consent.is_(True))
        .scalar_subquery()
    )
    result = await db.execute(
        update(Turn)
        .where(
            Turn.session_id.in_(session_ids_subquery),
            Turn.speaker == "user",
            Turn.training_excluded.is_(False),
        )
        .values(training_excluded=True)
    )
    await db.flush()
    # `update()` executes as a CursorResult at runtime, which has `.rowcount` — the async
    # `Result[Any]` static type doesn't expose it.
    excluded_count = result.rowcount or 0  # type: ignore[attr-defined]
    logger.info(
        "training_consent_revoked",
        user_id=str(user_id),
        turns_excluded=excluded_count,
    )
    return excluded_count


# ── Task 4.4 — BYOK provider credentials ──────────────────────────────────────────────────────


async def get_provider_credential(
    db: AsyncSession, user_id: std_uuid.UUID, provider: str
) -> ProviderCredential | None:
    result = await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.user_id == user_id, ProviderCredential.provider == provider
        )
    )
    return result.scalar_one_or_none()


async def list_provider_credentials(
    db: AsyncSession, user_id: std_uuid.UUID
) -> list[ProviderCredential]:
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.user_id == user_id)
    )
    return list(result.scalars().all())


async def upsert_provider_credential(
    db: AsyncSession, user_id: std_uuid.UUID, *, provider: str, api_key: str
) -> ProviderCredential:
    credential = await get_provider_credential(db, user_id, provider)
    encrypted = encrypt_secret(api_key)
    if credential is None:
        credential = ProviderCredential(
            user_id=user_id, provider=provider, encrypted_api_key=encrypted
        )
        db.add(credential)
    else:
        credential.encrypted_api_key = encrypted
        # A new key invalidates whatever the old key's connection test proved.
        credential.last_test_status = "untested"
        credential.last_tested_at = None
    await db.flush()
    return credential


async def delete_provider_credential(
    db: AsyncSession, user_id: std_uuid.UUID, provider: str
) -> None:
    credential = await get_provider_credential(db, user_id, provider)
    if credential is not None:
        await db.delete(credential)
        await db.flush()


async def test_provider_connection(
    db: AsyncSession, user_id: std_uuid.UUID, provider: str
) -> tuple[bool, str]:
    """Task 4.4: "a connection test per provider." A real, minimal request against the
    provider's own API — not a format check on the key string — so "success" actually means
    the key works. `services/api` doesn't otherwise call any inference provider (CLAUDE.md §2:
    model calls belong to realtime/coach), but a settings-page connectivity check is a
    deliberately different thing from running the product's own inference, so a direct httpx
    call here (rather than pulling in litellm as a new dependency for one lightweight probe)
    keeps that boundary intentional rather than accidental.
    """
    credential = await get_provider_credential(db, user_id, provider)
    if credential is None:
        return False, "No API key saved for this provider yet."

    api_key = decrypt_secret(credential.encrypted_api_key)
    success: bool
    message: str
    try:
        async with httpx.AsyncClient(timeout=CONNECTION_TEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                GROQ_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": CONNECTION_TEST_MODEL,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
        if resp.status_code == 200:
            success, message = True, "Connected successfully."
        elif resp.status_code == 401:
            success, message = False, "The API key was rejected — check it and try again."
        elif resp.status_code == 429:
            success, message = True, "Key is valid (currently rate-limited)."
        else:
            success, message = False, f"Provider returned HTTP {resp.status_code}."
    except httpx.TimeoutException:
        success, message = False, "The provider did not respond in time."
    except httpx.HTTPError as exc:
        success, message = False, f"Could not reach the provider: {exc}"

    credential.last_test_status = "success" if success else "failed"
    credential.last_tested_at = datetime.now(UTC)
    await db.flush()
    return success, message


# ── Task 4.4 — export ─────────────────────────────────────────────────────────────────────────


async def export_user_data(db: AsyncSession, user_id: std_uuid.UUID) -> dict[str, object]:
    """Task 4.4's Privacy section: "Export produces a JSON archive of profile, sessions,
    transcripts and scores." Deliberately excludes `encrypted_api_key` (BYOK secrets are never
    exported in any form) and raw audio (CLAUDE.md §8: audio is regenerable/re-fetchable via
    the recording endpoint, not duplicated into an export archive)."""
    from . import session_service  # local import: avoids a service<->service import cycle

    user = await db.get(User, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found.")
    profile = await get_profile(db, user_id)

    sessions_result = await db.execute(select(Session).where(Session.user_id == user_id))
    sessions = list(sessions_result.scalars().all())

    sessions_export: list[dict[str, object]] = []
    for session in sessions:
        turns = await session_service.list_turns_with_scores(db, session.id)
        sessions_export.append(
            {
                "id": str(session.id),
                "scenario_id": str(session.scenario_id),
                "status": session.status,
                "created_at": session.created_at.isoformat(),
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "duration_ms": session.duration_ms,
                "target_minutes": session.target_minutes,
                "turns": [t.model_dump(mode="json") for t in turns],
            }
        )

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at.isoformat(),
        },
        "profile": {
            "target_role": profile.target_role if profile else None,
            "goal": profile.goal if profile else None,
            "experience_level": profile.experience_level if profile else None,
            "resume_text": profile.resume_text if profile else None,
        }
        if profile
        else None,
        "sessions": sessions_export,
    }


async def delete_user_and_all_data(db: AsyncSession, user_id: std_uuid.UUID) -> None:
    """AS-05 — genuine, full deletion. FK ON DELETE CASCADE handles every DB row transitively
    owned by this user (profiles, sessions, and everything hanging off sessions); the S3 prefix
    is purged separately since object storage isn't part of the FK graph.
    """
    user = await db.get(User, user_id)
    if user is None:
        return
    await delete_prefix(f"users/{user_id}/")
    await db.delete(user)
    await db.flush()
