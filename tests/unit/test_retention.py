"""docs/phase-4-BUILD.md TASK 4.4: "Retention setting is honoured by the expiry job." Pure
decision logic under test — see scripts/expire_recordings.py for the I/O wrapper around this."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.api.app.services.retention import RecordingRecord, is_recording_expired

NOW = datetime(2026, 8, 23, tzinfo=UTC)


def _record(**overrides: object) -> RecordingRecord:
    defaults: dict[str, object] = {
        "session_id": "s1",
        "recording_key": "users/u1/sessions/s1.opus",
        "ended_at": NOW - timedelta(days=10),
        "retention_days": 30,
        "report_status": "ready",
    }
    defaults.update(overrides)
    return RecordingRecord(**defaults)  # type: ignore[arg-type]


class TestDefaultRetention:
    def test_not_expired_before_the_window_elapses(self) -> None:
        record = _record(ended_at=NOW - timedelta(days=10), retention_days=30)
        assert is_recording_expired(record, now=NOW) is False

    def test_expired_once_the_window_has_fully_elapsed(self) -> None:
        record = _record(ended_at=NOW - timedelta(days=31), retention_days=30)
        assert is_recording_expired(record, now=NOW) is True

    def test_expires_exactly_at_the_boundary(self) -> None:
        record = _record(ended_at=NOW - timedelta(days=30), retention_days=30)
        assert is_recording_expired(record, now=NOW) is True


class TestImmediateAfterScoring:
    def test_not_expired_before_the_report_is_ready(self) -> None:
        record = _record(retention_days=0, report_status=None, ended_at=NOW - timedelta(days=5))
        assert is_recording_expired(record, now=NOW) is False

    def test_not_expired_while_report_is_still_pending(self) -> None:
        record = _record(
            retention_days=0, report_status="pending", ended_at=NOW - timedelta(days=5)
        )
        assert is_recording_expired(record, now=NOW) is False

    def test_expired_the_instant_the_report_is_ready_regardless_of_elapsed_time(self) -> None:
        record = _record(
            retention_days=0, report_status="ready", ended_at=NOW - timedelta(minutes=1)
        )
        assert is_recording_expired(record, now=NOW) is True


class TestUnfinishedSession:
    def test_never_expired_without_an_ended_at(self) -> None:
        record = _record(ended_at=None, retention_days=0, report_status="ready")
        assert is_recording_expired(record, now=NOW) is False
