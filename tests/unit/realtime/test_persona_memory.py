"""docs/phase-2-BUILD.md TASK 2.3d: memory compaction. `summarize_history`'s real model call is
covered live in test_persona_live.py; this file covers the pure split and the never-raises
failure fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.realtime.app.persona.memory import (
    RECENT_TURNS_VERBATIM,
    split_recent_and_older,
    summarize_history,
)


def _history(n: int) -> list[dict[str, str]]:
    return [{"speaker": "user" if i % 2 else "persona", "text": f"turn {i}"} for i in range(n)]


class TestSplitRecentAndOlder:
    def test_short_history_is_entirely_recent(self) -> None:
        history = _history(3)
        older, recent = split_recent_and_older(history)
        assert older == []
        assert recent == history

    def test_exactly_at_the_boundary_is_entirely_recent(self) -> None:
        history = _history(RECENT_TURNS_VERBATIM)
        older, recent = split_recent_and_older(history)
        assert older == []
        assert len(recent) == RECENT_TURNS_VERBATIM

    def test_longer_history_splits_correctly(self) -> None:
        history = _history(10)
        older, recent = split_recent_and_older(history)
        assert len(older) == 10 - RECENT_TURNS_VERBATIM
        assert len(recent) == RECENT_TURNS_VERBATIM
        assert recent == history[-RECENT_TURNS_VERBATIM:]
        assert older == history[:-RECENT_TURNS_VERBATIM]


class TestSummarizeHistory:
    @pytest.mark.asyncio
    async def test_no_older_turns_returns_previous_summary_unchanged(self) -> None:
        result = await summarize_history(
            "fake/model", previous_summary="prior notes", older_turns=[]
        )
        assert result == "prior notes"

    @pytest.mark.asyncio
    async def test_model_failure_falls_back_to_previous_summary(self) -> None:
        """Task 2.3's general degrade-gracefully pattern: a failed compaction never breaks the
        session, it just means the next turn carries stale (but still useful) context."""
        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=ConnectionError):
            result = await summarize_history(
                "fake/model", previous_summary="prior notes", older_turns=_history(2)
            )
        assert result == "prior notes"
