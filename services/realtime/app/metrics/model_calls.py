"""Every model invocation writes a `model_calls` row — no exceptions, no sampling (CLAUDE.md
§8, Task 1.6a). Unlike latency events this isn't batched: a model call is already a
multi-hundred-millisecond event, so one more small insert after it completes is immaterial to
the budget, and cost/token accounting is exactly the kind of row you don't want to lose to a
crash before a batched flush.
"""

from __future__ import annotations

import uuid as std_uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..core.ids import uuid7

ModelCallWriter = Callable[..., Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ModelCallRecord:
    session_id: std_uuid.UUID
    turn_id: std_uuid.UUID | None
    role: str
    model: str
    prompt_version: str | None
    tokens_in: int
    tokens_out: int
    ttft_ms: float | None
    total_latency_ms: float
    cost_cents: float = 0.0
    cached: bool = False


async def record_model_call(writer: ModelCallWriter, record: ModelCallRecord) -> None:
    await writer(
        call_id=uuid7(),
        session_id=record.session_id,
        turn_id=record.turn_id,
        role=record.role,
        model=record.model,
        prompt_version=record.prompt_version,
        tokens_in=record.tokens_in,
        tokens_out=record.tokens_out,
        ttft_ms=record.ttft_ms,
        total_latency_ms=record.total_latency_ms,
        cost_cents=record.cost_cents,
        cached=record.cached,
    )
