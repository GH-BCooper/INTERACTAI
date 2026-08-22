"""Declarative base and shared mixins for every InteractAI table.

Universal requirements (CLAUDE.md §5, docs/phase-0-BUILD.md TASK 0.4):
  - UUID v7 primary keys, so rows sort by creation time in the index.
  - created_at / updated_at, timezone-aware UTC, server-side defaults.

Enum-like columns (status, archetype, family, ...) are plain String + CheckConstraint rather
than native Postgres ENUM types: adding a value to a native enum requires ALTER TYPE ...
ADD VALUE, which cannot run inside a transaction block in older Postgres and complicates
autogenerate diffing. A CHECK constraint is one ALTER TABLE away from widening.
"""

from __future__ import annotations

import uuid as std_uuid
from datetime import datetime

import uuid_utils
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uuid7() -> std_uuid.UUID:
    """UUID v7 (RFC 9562): embeds a millisecond timestamp in the high bits, so primary keys
    sort by creation time and B-tree inserts stay append-mostly. See docs/phase-0-LEARN.md §5.
    """
    return std_uuid.UUID(bytes=uuid_utils.uuid7().bytes)


class Base(DeclarativeBase):
    pass


class UUIDPk:
    """Non-partitioned tables: a plain single-column UUIDv7 primary key."""

    id: Mapped[std_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def sql_in(column: str, values: tuple[str, ...]) -> str:
    """Render a CheckConstraint expression for an enum-like column. See module docstring for
    why these are CHECK constraints rather than native Postgres ENUM types.
    """
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"
