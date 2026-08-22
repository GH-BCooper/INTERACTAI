"""Task 2.5c: "record the cost honestly in model_calls — this figure becomes the counterfactual
in the observability cost panel." Shared by the scorer and the narrator, both of which make raw
`litellm.acompletion` calls and need the same extraction logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import litellm


@dataclass(frozen=True, slots=True)
class CallStats:
    tokens_in: int
    tokens_out: int
    total_latency_ms: float
    cost_cents: float
    cached: bool


def extract_call_stats(response: Any, *, total_latency_ms: float) -> CallStats:
    usage = getattr(response, "usage", None)
    tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
    try:
        cost_usd = float(litellm.completion_cost(completion_response=response) or 0.0)
    except Exception:
        cost_usd = 0.0
    hidden = getattr(response, "_hidden_params", {}) or {}
    cached = bool(hidden.get("cache_hit", False))
    return CallStats(
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_latency_ms=total_latency_ms,
        cost_cents=round(cost_usd * 100, 6),
        cached=cached,
    )
