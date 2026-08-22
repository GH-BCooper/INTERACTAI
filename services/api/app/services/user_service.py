"""No raw SQL in routers (CLAUDE.md §5) — repository functions live here."""

from __future__ import annotations

import uuid as std_uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.s3 import delete_prefix
from ..models import Profile, User


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
    resume_text: str | None,
    target_role: str | None,
    clear_resume: bool,
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

    await db.flush()
    return profile


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
