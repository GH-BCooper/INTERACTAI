"""UUIDv7 generation — mirrors services/api/app/models/base.py's `uuid7()` exactly (same
`uuid_utils` dependency, same rationale: CLAUDE.md §5, primary keys sort by creation time).
Realtime doesn't import api's module (docs/decisions/0003), so this is the local copy.
"""

from __future__ import annotations

import uuid as std_uuid

import uuid_utils


def uuid7() -> std_uuid.UUID:
    return std_uuid.UUID(bytes=uuid_utils.uuid7().bytes)
