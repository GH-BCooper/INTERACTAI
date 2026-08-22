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
    # docs/phase-3-BUILD.md TASK 3.3a/3.4d — NULL until the recording finalizes, or forever if
    # the session never captured any user audio (CLAUDE.md §10: never fabricate a metric).
    recording_available: bool
    retry_of_session_id: UUID | None
    retry_of_turn_id: UUID | None


class WsTokenOut(BaseModel):
    token: str
    expires_in: int
    ws_url: str


class ReplayTokenOut(BaseModel):
    """Task 3.4d — scopes the browser's direct calls to realtime's `POST /synthesize` for
    on-demand persona-audio regeneration during report replay."""

    token: str
    expires_in: int


class RecordingOut(BaseModel):
    """Task 3.3a/3.3f. `url` is a short-lived presigned GET against S3/MinIO — api mints the URL
    but never reads the object itself (CLAUDE.md §2: api never touches audio). `None` fields
    mean no recording exists for this session (never captured, or storage not configured); the
    report UI must degrade gracefully (Task 3.4's edge-case table), never show an error."""

    url: str | None
    format: Literal["wav", "opus"] | None
    peaks: list[float] | None
    duration_ms: int | None


class NextActionOut(BaseModel):
    text: str
    turn_id: UUID | None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    status: str
    summary: str | None
    strengths: list[str]
    growth_areas: list[str]
    next_actions: list[NextActionOut]
    highlight_turn_id: UUID | None
    lowlight_turn_id: UUID | None
    low_sample_size: bool
    generated_at: datetime | None


class WordTimingOut(BaseModel):
    word: str
    start_ms: int
    end_ms: int


class TurnScoreOut(BaseModel):
    criterion_key: str
    # NULL when confidence was below the gating threshold — CLAUDE.md §1.6: "not enough signal",
    # never a number. Already gated server-side by services/coach; this schema only ever passes
    # the stored value through, never re-derives it.
    score: int | None
    confidence: float
    evidence_spans: list[dict[str, int]]
    model_version: str


class TurnMetricsOut(BaseModel):
    """Deterministic only (CLAUDE.md §5) — rendered with different visual treatment than
    `TurnScoreOut` in the report UI so arithmetic is never confused with judgement."""

    model_config = ConfigDict(from_attributes=True)

    wpm: float
    filler_count: int
    filler_rate: float
    longest_pause_ms: int
    speech_ratio: float
    word_count: int


class TurnOut(BaseModel):
    id: UUID
    index: int
    speaker: Literal["user", "persona"]
    text: str
    start_ms: int
    end_ms: int
    word_timings: list[WordTimingOut]
    truncated: bool
    asr_confidence: float | None
    metrics: TurnMetricsOut | None
    scores: list[TurnScoreOut]


class SessionScoreOut(BaseModel):
    """The session-level rollup a report's score panel renders (CLAUDE.md §5: distinct from any
    single turn's judgement). `name`/`anchor_descriptors` are joined in from the rubric so the
    UI can show "the same words the annotator saw" (Task 3.3d) without a second round trip."""

    criterion_key: str
    name: str
    aggregate_score: float | None
    confidence: float
    percentile_vs_self: float | None
    evidence_turn_ids: list[UUID]
    anchor_descriptors: dict[str, str]


class AnnotationCreate(BaseModel):
    """Task 3.4e. `round` is intentionally absent here — the server always assigns the next
    round for this (turn, annotator, criterion), so the same reviewer can label the same turn
    more than once across visits without colliding on the DB's uniqueness constraint."""

    turn_id: UUID
    criterion_key: str
    score: int = Field(ge=1, le=5)
    notes: str | None = None


class AnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    turn_id: UUID
    criterion_key: str
    round: int
    score: int
    notes: str | None
    created_at: datetime


class RetryCreate(BaseModel):
    """Task 3.4f — "retry one question": re-runs a single question in isolation, in the same
    scenario and difficulty as the turn it re-asks."""

    turn_id: UUID
