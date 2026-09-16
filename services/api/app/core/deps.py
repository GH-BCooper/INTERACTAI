from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..services.user_service import get_user_by_id
from .db import get_db
from .exceptions import AuthInvalidTokenError, ForbiddenError
from .security import decode_access_token

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthInvalidTokenError("Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    claims = decode_access_token(token)
    user = await get_user_by_id(db, UUID(claims.user_id))
    if user is None or not user.is_active:
        raise AuthInvalidTokenError("User no longer exists.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin_user(user: CurrentUser) -> User:
    """docs/phase-5-BUILD.md TASK 5.3a: "/app/annotate (admin only)." No role system exists
    anywhere else in this project (docs/decisions/0019) — a single boolean, granted only via
    scripts/grant_admin.py, is the whole of what "admin" means here.
    """
    if not user.is_admin:
        raise ForbiddenError("This tool is restricted to admin accounts.")
    return user


AdminUser = Annotated[User, Depends(get_current_admin_user)]
