from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TargetMinutes = Literal[5, 10, 20, 30]


class SessionCreate(BaseModel):
    scenario_id: UUID
    difficulty: Literal["gentle", "standard", "hard"]
    target_minutes: TargetMinutes
    focus_areas: list[str] = Field(default_factory=list)
    resume_text_override: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario_id: UUID
    status: str
    end_reason: str | None
    target_minutes: int
    focus_areas: list[str]
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    created_at: datetime


class WsTokenOut(BaseModel):
    token: str
    expires_in: int
    ws_url: str


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    status: str
    summary: str | None
    strengths: list[str]
    growth_areas: list[str]
    generated_at: datetime | None
