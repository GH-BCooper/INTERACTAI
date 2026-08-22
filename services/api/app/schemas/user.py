from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None
    avatar_url: str | None
    created_at: datetime


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resume_text: str | None
    resume_updated_at: datetime | None
    target_role: str | None


class MeOut(BaseModel):
    user: UserOut
    profile: ProfileOut | None


class ProfileUpdate(BaseModel):
    """PATCH /me/profile. Omit a field to leave it unchanged; send null to clear it —
    resume_text is independently deletable without deleting the profile (Task 0.4).
    """

    resume_text: str | None = Field(default=None)
    target_role: str | None = Field(default=None)
    clear_resume: bool = False
