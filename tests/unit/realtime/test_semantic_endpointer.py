"""Live smoke test against the real MODEL_ENDPOINTER (ollama/qwen2.5:0.5b-instruct). Skipped
when Ollama isn't reachable — this is the one piece of Phase 1 that depends on infrastructure
outside this repo, so CI (no local Ollama) skips it rather than failing."""

from __future__ import annotations

import httpx
import pytest

from services.realtime.app.core.config import get_settings
from services.realtime.app.endpointing.semantic import check_semantic_completeness


def _ollama_reachable() -> bool:
    try:
        httpx.get(f"{get_settings().ollama_base_url}/api/tags", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not reachable")


@pytest.mark.asyncio
async def test_recognizes_a_complete_sentence() -> None:
    """qwen2.5:0.5b-instruct is fast, not reliable — see the module docstring. This case is
    the one this repo verified it gets right with the few-shot prompt; it is not a claim the
    model is accurate in general."""
    model = get_settings().model_endpointer
    result = await check_semantic_completeness(model, "That's the whole story.")
    assert result is True


@pytest.mark.asyncio
async def test_recognizes_an_incomplete_fragment() -> None:
    model = get_settings().model_endpointer
    result = await check_semantic_completeness(model, "so I was thinking, um")
    assert result is False


@pytest.mark.asyncio
async def test_empty_tail_is_treated_as_complete() -> None:
    model = get_settings().model_endpointer
    assert await check_semantic_completeness(model, "") is True
    assert await check_semantic_completeness(model, "   ") is True
