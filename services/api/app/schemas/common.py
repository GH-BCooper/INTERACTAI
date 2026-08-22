from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    recovery: str
    fatal: bool
    trace_id: str


class ErrorResponse(BaseModel):
    """The frozen error shape — CLAUDE.md §6."""

    error: ErrorBody


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
