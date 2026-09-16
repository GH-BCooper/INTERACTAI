#!/usr/bin/env python3
"""docs/decisions/0019: the whole of this project's "admin" concept is one boolean, granted only
here — never through a public endpoint. Usage:

    uv run python scripts/grant_admin.py user@example.com
    uv run python scripts/grant_admin.py user@example.com --revoke
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"
for _path in (str(REPO_ROOT), str(API_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models import User  # noqa: E402


async def set_admin(email: str, *, is_admin: bool) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None:
                print(f"No user with email {email!r}.", file=sys.stderr)
                return 1
            user.is_admin = is_admin
            await db.commit()
            print(f"{email}: is_admin = {is_admin}")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    return asyncio.run(set_admin(args.email, is_admin=not args.revoke))


if __name__ == "__main__":
    raise SystemExit(main())
