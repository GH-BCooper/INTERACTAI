"""Task 2.2a: resume replay. `sent_message_log` (session.py) is populated by
`WsTurnSink._send_control` (sink.py) in production; here it's populated directly, since what's
under test is the replay selection/ordering logic in `main.py::_replay_missed_messages`, not the
sink's own send path (that's covered by test_state_machine.py and friends exercising
`send_state_change` etc.)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from services.realtime.app.main import _replay_missed_messages
from services.realtime.app.session import SessionRuntime


class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def send_bytes(self, data: bytes) -> None:  # pragma: no cover - unused here
        pass


def _runtime() -> SessionRuntime:
    return SessionRuntime(session_id=uuid.uuid4(), user_id=uuid.uuid4(), websocket=_FakeSocket())


async def _drain() -> None:
    """`_replay_missed_messages` fires `asyncio.ensure_future` per replayed message rather than
    awaiting them inline (Task 2.2a's replay must not block the caller) — yield back to the
    loop so those scheduled sends actually run before assertions."""
    await asyncio.sleep(0)
    await asyncio.sleep(0)


class TestReplayMissedMessages:
    @pytest.mark.asyncio
    async def test_replays_only_messages_after_last_server_seq(self) -> None:
        rt = _runtime()
        for seq in range(5):
            rt.sent_message_log.append((seq, f"msg-{seq}"))

        count = _replay_missed_messages(rt.websocket, rt, last_server_seq=2)
        await _drain()

        assert count == 2
        assert rt.websocket.sent == ["msg-3", "msg-4"]

    @pytest.mark.asyncio
    async def test_nothing_missed_replays_nothing(self) -> None:
        rt = _runtime()
        for seq in range(5):
            rt.sent_message_log.append((seq, f"msg-{seq}"))

        count = _replay_missed_messages(rt.websocket, rt, last_server_seq=4)
        await _drain()

        assert count == 0
        assert rt.websocket.sent == []

    @pytest.mark.asyncio
    async def test_empty_log_replays_nothing(self) -> None:
        rt = _runtime()
        count = _replay_missed_messages(rt.websocket, rt, last_server_seq=0)
        await _drain()
        assert count == 0
        assert rt.websocket.sent == []

    def test_ring_buffer_caps_at_100_oldest_dropped_first(self) -> None:
        rt = _runtime()
        for seq in range(150):
            rt.sent_message_log.append((seq, f"msg-{seq}"))
        assert len(rt.sent_message_log) == 100
        oldest_kept_seq, _ = rt.sent_message_log[0]
        assert oldest_kept_seq == 50  # the first 50 (0-49) were pushed out
