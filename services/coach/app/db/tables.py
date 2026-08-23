"""SQLAlchemy Core mirrors of the tables coach reads or writes — same pattern and rationale as
services/realtime/app/db/tables.py (docs/decisions/0003): coach is an independent uv workspace
member and never imports services/api's ORM classes. Column definitions must stay byte-for-byte
in sync with services/api/app/models/{session,turn,scoring,content,observability,jobs}.py.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

metadata = MetaData()

scenarios = Table(
    "scenarios",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("family", Text, nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("user_id", PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("scenario_id", PGUUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False),
    Column("status", Text, nullable=False),
    Column("end_reason", Text),
    Column("target_minutes", Integer, nullable=False),
    Column("brief", JSONB, nullable=False),
    Column("question_plan", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# Partitioned by month on created_at (docs/decisions/0002) — coach only ever reads by id/
# session_id, never needs the composite (id, created_at) key a partition-aware write would.
turns = Table(
    "turns",
    metadata,
    Column("id", PGUUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("index", Integer, nullable=False),
    Column("speaker", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("start_ms", Integer, nullable=False),
    Column("end_ms", Integer, nullable=False),
    Column("truncated", Boolean, nullable=False),
    Column("asr_confidence", Float),
    Column("text_scrubbed", Text),
)

turn_metrics = Table(
    "turn_metrics",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("turn_id", PGUUID(as_uuid=True), nullable=False),
    Column("wpm", Float, nullable=False),
    Column("filler_count", Integer, nullable=False),
    Column("filler_rate", Float, nullable=False),
    Column("longest_pause_ms", Integer, nullable=False),
    Column("speech_ratio", Float, nullable=False),
    Column("word_count", Integer, nullable=False),
)

turn_scores = Table(
    "turn_scores",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("turn_id", PGUUID(as_uuid=True), nullable=False),
    Column("criterion_key", Text, nullable=False),
    Column("score", Integer),
    Column("confidence", Float, nullable=False),
    Column("evidence_spans", JSONB, nullable=False),
    Column("model_version", Text, nullable=False),
    Column("rationale", Text),
)

session_scores = Table(
    "session_scores",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("criterion_key", Text, nullable=False),
    Column("aggregate_score", Float),
    Column("confidence", Float, nullable=False),
    Column("evidence_turn_ids", ARRAY(Text), nullable=False),
    Column("model_version", Text, nullable=False),
    Column("percentile_vs_self", Float),
)

reports = Table(
    "reports",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("status", Text, nullable=False),
    Column("summary", Text),
    Column("strengths", ARRAY(Text), nullable=False),
    Column("growth_areas", ARRAY(Text), nullable=False),
    Column("next_actions", JSONB, nullable=False),
    Column("highlight_turn_id", PGUUID(as_uuid=True)),
    Column("lowlight_turn_id", PGUUID(as_uuid=True)),
    Column("low_sample_size", Boolean, nullable=False),
    Column("narrator_model_version", Text),
    Column("generated_at", DateTime(timezone=True)),
)

rubrics = Table(
    "rubrics",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("slug", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("aggregation_policy", JSONB, nullable=False),
)

rubric_criteria = Table(
    "rubric_criteria",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("rubric_id", PGUUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False),
    Column("key", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("anchor_descriptors", JSONB, nullable=False),
)

model_calls = Table(
    "model_calls",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("turn_id", PGUUID(as_uuid=True)),
    Column("role", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("prompt_version", Text),
    Column("tokens_in", Integer, nullable=False),
    Column("tokens_out", Integer, nullable=False),
    Column("ttft_ms", Float),
    Column("total_latency_ms", Float, nullable=False),
    Column("cost_cents", Numeric(10, 6), nullable=False),
    Column("cached", Boolean, nullable=False),
)

failed_jobs = Table(
    "failed_jobs",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("turn_id", PGUUID(as_uuid=True)),
    Column("job_name", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("error", Text, nullable=False),
    Column("attempts", Integer, nullable=False),
)
