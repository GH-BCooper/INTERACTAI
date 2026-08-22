"""SQLAlchemy Core mirrors of the tables realtime reads or writes.

Deliberately Core `Table` objects, not the ORM classes from services/api/app/models — realtime
and api are independent uv workspace members (CLAUDE.md §2) and neither imports the other's
application code; the schema itself (owned by api's Alembic migrations) is the shared contract.
A Core mirror is the standard way to consume a table you don't own: it round-trips the exact
columns realtime touches without pulling in api's ORM relationships, routers or settings.
See docs/decisions/0003-realtime-db-access.md for why this was worth writing down.

Column definitions must stay byte-for-byte in sync with services/api/app/models/{session,turn,
observability}.py. tests/integration covers this by inserting through these Table objects
against the real (Alembic-migrated) schema.
"""

from __future__ import annotations

from sqlalchemy import (
    ARRAY,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

metadata = MetaData()

sessions = Table(
    "sessions",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("user_id", PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("scenario_id", PGUUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False),
    Column("status", Text, nullable=False),
    Column("end_reason", Text),
    Column("target_minutes", Integer, nullable=False),
    Column("focus_areas", ARRAY(Text), nullable=False),
    Column("resume_text_override", Text),
    Column("brief", JSONB, nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("ended_at", DateTime(timezone=True)),
    Column("duration_ms", Integer),
    Column("question_plan", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# Partitioned by month on created_at (docs/decisions/0002-turns-partitioning-and-fk.md); PK is
# composite (id, created_at) there, but realtime only ever inserts — it never needs the
# composite key for a lookup, so a plain `id` Column (not marked primary_key here) is enough.
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
    Column("word_timings", JSONB, nullable=False),
    Column("truncated", Boolean, nullable=False),
    Column("asr_confidence", Float),
)

turn_metrics = Table(
    "turn_metrics",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("turn_id", PGUUID(as_uuid=True), nullable=False),
    Column("wpm", Float, nullable=False),
    Column("filler_count", Integer, nullable=False),
    Column("filler_rate", Float, nullable=False),
    Column("longest_pause_ms", Integer, nullable=False),
    Column("speech_ratio", Float, nullable=False),
    Column("word_count", Integer, nullable=False),
)

latency_events = Table(
    "latency_events",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("session_id", PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False),
    Column("turn_id", PGUUID(as_uuid=True), nullable=False),
    Column("stage", Text, nullable=False),
    Column("duration_ms", Float, nullable=False),
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
