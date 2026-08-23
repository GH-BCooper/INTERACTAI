"""Task 4.4/CLAUDE.md §10 (AS-03): "Default retention 30 days, configurable down to 'delete
immediately after scoring'." Pure decision logic — no DB, no S3 — so scripts/expire_recordings.py
stays a thin loop around this and is honestly testable without touching real infrastructure for
the decision itself (the actual deletion is I/O and is exercised in the integration test that
asserts zero remaining S3 objects under the user prefix, per Task 4.4's own acceptance line).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

IMMEDIATE_AFTER_SCORING_RETENTION_DAYS = 0


@dataclass(frozen=True, slots=True)
class RecordingRecord:
    session_id: str
    recording_key: str
    ended_at: datetime | None
    retention_days: int
    report_status: str | None  # None if no report row exists yet


def is_recording_expired(record: RecordingRecord, *, now: datetime) -> bool:
    """A session with no `ended_at` yet is never expired — it hasn't finished, so there is
    nothing to measure retention from. `retention_days == 0` means "delete immediately after
    scoring": expiry then depends on the report existing and being ready, not on elapsed time
    at all."""
    if record.ended_at is None:
        return False
    if record.retention_days == IMMEDIATE_AFTER_SCORING_RETENTION_DAYS:
        return record.report_status == "ready"
    return now >= record.ended_at + timedelta(days=record.retention_days)
