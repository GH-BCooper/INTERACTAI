#!/usr/bin/env python3
"""Keep `turns`' monthly partitions rolling forward.

The initial migration only guarantees the current and next month exist (it has to — a
migration can't know the future). Run this periodically (a monthly cron job in production) to
keep `--months-ahead` partitions always created in advance of `turns_default` ever being hit.

Usage:
    uv run python scripts/create_turn_partitions.py [--months-ahead 3]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from app.core.config import get_settings  # noqa: E402


async def ensure_partitions(months_ahead: int) -> list[str]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    created: list[str] = []
    try:
        async with engine.begin() as conn:
            now = datetime.now(UTC).replace(day=1)
            for i in range(months_ahead + 1):  # +1: this month itself, then N ahead
                month_start = now + relativedelta(months=i)
                month_end = month_start + relativedelta(months=1)
                name = f"turns_{month_start.year:04d}_{month_start.month:02d}"
                await conn.execute(
                    text(
                        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF turns "
                        f"FOR VALUES FROM ('{month_start.date().isoformat()}') "
                        f"TO ('{month_end.date().isoformat()}')"
                    )
                )
                created.append(name)
    finally:
        await engine.dispose()
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months-ahead", type=int, default=3, help="how many months beyond the current one"
    )
    args = parser.parse_args()

    created = asyncio.run(ensure_partitions(args.months_ahead))
    for name in created:
        print(f"ensured partition: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
