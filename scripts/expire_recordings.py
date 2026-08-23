#!/usr/bin/env python3
"""Task 4.4/AS-03: purges recordings past each user's own retention setting.

Not on any request path — a periodic job (cron / scheduled task in deployment), same category
as scripts/create_turn_partitions.py. Deletes the S3/MinIO object and nulls
`sessions.recording_key` / `.recording_format` / `.peaks` so the report UI's existing "Recording
deleted (retention expired)" edge case (Task 3.4) renders correctly — no new UI branch needed,
this script produces exactly the state that branch already handles.

Usage: uv run python scripts/expire_recordings.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"
for _path in (str(REPO_ROOT), str(API_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.core.s3 import get_s3_client  # noqa: E402
from app.models import Report, Session, User  # noqa: E402
from app.services.retention import RecordingRecord, is_recording_expired  # noqa: E402

logger = get_logger(__name__)


async def _find_expired(db: AsyncSession, *, now: datetime) -> list[Session]:
    result = await db.execute(
        select(Session, User.audio_retention_days, Report.status)
        .join(User, User.id == Session.user_id)
        .outerjoin(Report, Report.session_id == Session.id)
        .where(Session.recording_key.is_not(None))
    )
    expired: list[Session] = []
    for session, retention_days, report_status in result.all():
        record = RecordingRecord(
            session_id=str(session.id),
            recording_key=session.recording_key,
            ended_at=session.ended_at,
            retention_days=retention_days,
            report_status=report_status,
        )
        if is_recording_expired(record, now=now):
            expired.append(session)
    return expired


def _delete_object_sync(key: str) -> None:
    settings = get_settings()
    get_s3_client().delete_object(Bucket=settings.s3_bucket, Key=key)


async def run(*, dry_run: bool) -> int:
    configure_logging()
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(UTC)

    purged = 0
    async with session_factory() as db:
        expired_sessions = await _find_expired(db, now=now)
        for session in expired_sessions:
            key = session.recording_key
            logger.info(
                "recording_expiring",
                session_id=str(session.id),
                recording_key=key,
                dry_run=dry_run,
            )
            if not dry_run:
                await asyncio.to_thread(_delete_object_sync, key)
                session.recording_key = None
                session.recording_format = None
                session.peaks = None
            purged += 1
        if not dry_run:
            await db.commit()

    await engine.dispose()
    return purged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Log what would be purged without deleting anything."
    )
    args = parser.parse_args()
    purged = asyncio.run(run(dry_run=args.dry_run))
    verb = "Would purge" if args.dry_run else "Purged"
    print(f"{verb} {purged} expired recording(s).")


if __name__ == "__main__":
    main()
