from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Goal = Literal["job_interview", "technical_interview", "salary_negotiation"]
ExperienceLevel = Literal["student", "early_career", "mid_level", "senior", "staff_plus"]
ProviderName = Literal["groq"]
ConnectionTestStatus = Literal["untested", "success", "failed"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None
    avatar_url: str | None
    created_at: datetime
    onboarded_at: datetime | None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resume_text: str | None
    resume_updated_at: datetime | None
    target_role: str | None
    goal: Goal | None
    experience_level: ExperienceLevel | None
    focus_areas: list[str]
    captions_default: bool
    speaking_rate: float
    noise_suppression: bool
    echo_cancellation: bool


class MeOut(BaseModel):
    user: UserOut
    profile: ProfileOut | None
    # docs/phase-3-BUILD.md TASK 3.1: the sidebar's "practice-minutes-this-week meter".
    practice_minutes_this_week: int


class ProfileUpdate(BaseModel):
    """PATCH /me/profile. Omit a field to leave it unchanged; send null to clear it —
    resume_text is independently deletable without deleting the profile (Task 0.4). Also the
    one endpoint every onboarding step (Task 4.3) writes through — "User abandons at step 2 ->
    Progress saved; resuming returns to step 2" needs no separate "onboarding state" to track,
    since re-reading GET /me shows exactly which fields are already filled in.
    """

    resume_text: str | None = Field(default=None)
    target_role: str | None = Field(default=None)
    clear_resume: bool = False
    goal: Goal | None = Field(default=None)
    experience_level: ExperienceLevel | None = Field(default=None)
    focus_areas: list[str] | None = Field(default=None)
    captions_default: bool | None = Field(default=None)
    speaking_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    noise_suppression: bool | None = Field(default=None)
    echo_cancellation: bool | None = Field(default=None)


class PrivacySettingsOut(BaseModel):
    training_consent: bool
    audio_retention_days: int = Field(ge=0, le=365)


class PrivacySettingsUpdate(BaseModel):
    training_consent: bool | None = Field(default=None)
    audio_retention_days: int | None = Field(default=None, ge=0, le=365)


class ModelsSettingsOut(BaseModel):
    prefer_local_models: bool


class ModelsSettingsUpdate(BaseModel):
    prefer_local_models: bool | None = Field(default=None)


class ProviderCredentialOut(BaseModel):
    """The encrypted key itself never appears in any response body — only whether one is
    configured and the outcome of the last connection test (Task 4.4)."""

    model_config = ConfigDict(from_attributes=True)

    provider: ProviderName
    has_key: bool
    last_test_status: ConnectionTestStatus
    last_tested_at: datetime | None


class ProviderCredentialCreate(BaseModel):
    """`provider` is the URL path parameter on `PUT /me/providers/{provider}` — not repeated
    here, so there is nothing for the two to disagree about."""

    api_key: str = Field(min_length=1)


class ProviderConnectionTestOut(BaseModel):
    provider: ProviderName
    success: bool
    message: str
    tested_at: datetime
