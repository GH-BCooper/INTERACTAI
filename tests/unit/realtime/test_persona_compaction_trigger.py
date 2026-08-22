"""docs/phase-2-BUILD.md TASK 2.3d: the live wiring around `persona/memory.py` — fired from
`listening`, guarded so only one compaction runs at a time, and clears `turns_since_summary`
on success."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from services.realtime.app.frame_pipeline import _run_compaction
from services.realtime.app.session import SessionRuntime


class _FakeSocket:
    async def send_text(self, data: str) -> None:  # pragma: no cover
        pass

    async def send_bytes(self, data: bytes) -> None:  # pragma: no cover
        pass


def _runtime_with_history(n: int) -> SessionRuntime:
    rt = SessionRuntime(session_id=uuid.uuid4(), user_id=uuid.uuid4(), websocket=_FakeSocket())
    rt.persona_history = [
        {"speaker": "user" if i % 2 else "persona", "text": f"turn {i}"} for i in range(n)
    ]
    rt.turns_since_summary = n
    rt.compaction_in_flight = True  # simulates the caller's guard already having been set
    return rt


class TestRunCompaction:
    @pytest.mark.asyncio
    async def test_updates_summary_and_resets_counter(self) -> None:
        rt = _runtime_with_history(8)
        with patch(
            "services.realtime.app.frame_pipeline.summarize_history",
            new_callable=AsyncMock,
            return_value="a fresh summary",
        ):
            await _run_compaction(rt, "fake/model")
        assert rt.persona_history_summary == "a fresh summary"
        assert rt.turns_since_summary == 0

    @pytest.mark.asyncio
    async def test_always_clears_the_in_flight_guard_even_on_failure(self) -> None:
        rt = _runtime_with_history(8)
        with patch(
            "services.realtime.app.frame_pipeline.summarize_history",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError):
                await _run_compaction(rt, "fake/model")
        assert rt.compaction_in_flight is False

    @pytest.mark.asyncio
    async def test_short_history_is_a_no_op(self) -> None:
        """Fewer turns than the recent-verbatim window means there's nothing "older" to fold
        into a summary yet — `split_recent_and_older` returns an empty `older` list."""
        rt = _runtime_with_history(3)
        with patch(
            "services.realtime.app.frame_pipeline.summarize_history", new_callable=AsyncMock
        ) as mock_summarize:
            await _run_compaction(rt, "fake/model")
        mock_summarize.assert_not_called()
        assert rt.compaction_in_flight is False
