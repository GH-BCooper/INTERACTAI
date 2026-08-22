"""UUIDv7 generation — mirrors services/realtime/app/core/ids.py exactly (docs/decisions/0003:
coach is an independent workspace member, so this is the local copy, not a shared import)."""

from __future__ import annotations

import uuid as std_uuid

import uuid_utils


def uuid7() -> std_uuid.UUID:
    return std_uuid.UUID(bytes=uuid_utils.uuid7().bytes)
