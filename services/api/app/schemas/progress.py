from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

RecommendationKind = Literal["continue_session", "start_scenario"]


class RecommendationOut(BaseModel):
    """Task 4.1: "The reason is required, not decorative." Deterministic, no model call —
    services/api/app/services/progress_service.py::get_recommendation."""

    kind: RecommendationKind
    reason: str
    session_id: UUID | None = None
    scenario_id: UUID | None = None


class ProgressStripOut(BaseModel):
    sessions_this_week: int
    total_minutes_this_week: int
    overall_score: float | None
    overall_score_delta: float | None
    weakest_criterion_name: str | None


class RecentSessionOut(BaseModel):
    id: UUID
    scenario_title: str
    created_at: datetime
    duration_ms: int | None
    overall_score: float | None
    report_read: bool


AttentionKind = Literal["unread_report", "stalled_scenario", "declining_criterion"]


class AttentionItemOut(BaseModel):
    kind: AttentionKind
    text: str
    session_id: UUID | None = None
    scenario_id: UUID | None = None


class DashboardOut(BaseModel):
    recommendation: RecommendationOut
    progress_strip: ProgressStripOut
    recent_sessions: list[RecentSessionOut]
    attention: AttentionItemOut | None


class ScenarioAttemptOut(BaseModel):
    session_id: UUID
    created_at: datetime
    overall_score: float | None


class ScenarioProgressOut(BaseModel):
    attempts: int
    best_score: float | None
    # Task 4.2's scenario detail page: "previous attempts with scores and link to their
    # reports." Newest first, capped — a detail page, not a full audit log.
    recent_attempts: list[ScenarioAttemptOut]


class CriterionTrendPointOut(BaseModel):
    session_id: UUID
    created_at: datetime
    score: float


class CriterionTrendOut(BaseModel):
    criterion_key: str
    name: str
    points: list[CriterionTrendPointOut]


class WeeklyVolumePointOut(BaseModel):
    week_start: datetime
    minutes: int
    sessions: int


class PersonalBestOut(BaseModel):
    criterion_key: str
    name: str
    score: float
    session_id: UUID
    achieved_at: datetime


class WeakestDimensionOut(BaseModel):
    criterion_key: str
    name: str
    trend: float
    next_action: str


class ProgressOut(BaseModel):
    family: str
    families_available: list[str]
    criterion_trends: list[CriterionTrendOut]
    weekly_volume: list[WeeklyVolumePointOut]
    families_attempted: list[str]
    families_never_attempted: list[str]
    weakest_dimension: WeakestDimensionOut | None
    personal_bests: list[PersonalBestOut]
