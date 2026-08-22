from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..services.user_service import get_user_by_id
from .db import get_db
from .exceptions import AuthInvalidTokenError
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
