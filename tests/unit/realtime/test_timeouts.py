"""Task 2.1: "Force-failing ASR, TTS and the persona model each produce the correct degraded
behaviour." The pure timeout math (`StateMachine.is_expired`) is covered in
test_state_machine.py; this file covers the live side — the watchdog handlers in timeouts.py
that actually run when a timeout fires, using a fake sink that mimics `WsTurnSink`'s real
transition behaviour (it drives the same `StateMachine`) without any WebSocket or DB.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from services.realtime.app.schemas.ws import ServerMachineState as S
from services.realtime.app.session import SessionRuntime
from services.realtime.app.state_machine import DegradedInfo, StateMachine
from services.realtime.app.timeouts import (
    _handle_endpointing_timeout,
    _handle_idle_abandon,
    _handle_idle_prompt,
    _handle_speaking_timeout,
    _handle_thinking_timeout,
    run_state_watchdog,
)


class _FakeSocket:
    async def send_text(self, data: str) -> None:  # pragma: no cover
        pass

    async def send_bytes(self, data: bytes) -> None:  # pragma: no cover
        pass


class _FakeSink:
    """Mirrors just enough of `WsTurnSink`'s real behaviour (actually driving the
    `StateMachine`, per `sink.py::send_state_change`) for these tests to assert on the
    resulting state, not merely on "was some method called"."""

    def __init__(self, runtime: SessionRuntime) -> None:
        self.runtime = runtime
        self.degraded_calls: list[tuple[str, str, bool]] = []
        self.audio_chunks: list[tuple[object, int]] = []

    async def send_state_change(
        self,
        state: str,
        *,
        turn_id: object = None,
        component: str | None = None,
        recoverable: bool = True,
    ) -> None:
        server_state = S(state)
        degraded_info = (
            DegradedInfo(component=component, recoverable=recoverable)
            if server_state is S.degraded and component
            else None
        )
        self.runtime.state_machine.transition(server_state, degraded_info=degraded_info)

    async def send_degraded(self, component: str, message: str, recoverable: bool) -> None:
        self.degraded_calls.append((component, message, recoverable))

    async def send_audio_chunk(
        self, turn_id: object, chunk_seq: int, audio: object, sample_rate: int, is_final: bool
    ) -> None:
        self.audio_chunks.append((turn_id, chunk_seq))


class _FakeIdlePromptCache:
    def __init__(self, has_clip: bool) -> None:
        self._has_clip = has_clip

    def get(self, voice_id: str) -> object | None:
        if not self._has_clip:
            return None
        import numpy as np

        class _Clip:
            pcm = np.zeros(10, dtype="float32")
            sample_rate = 22050

        return _Clip()


class _FakeResources:
    def __init__(self, *, has_idle_prompt: bool = True) -> None:
        self.idle_prompt_cache = _FakeIdlePromptCache(has_idle_prompt)


def _runtime(state: S = S.idle) -> SessionRuntime:
    rt = SessionRuntime(session_id=uuid.uuid4(), user_id=uuid.uuid4(), websocket=_FakeSocket())
    rt.state_machine = StateMachine(state=state)
    return rt


class TestIdlePrompt:
    @pytest.mark.asyncio
    async def test_plays_the_idle_prompt_and_sets_the_once_per_visit_flag(self) -> None:
        rt = _runtime(S.idle)
        sink = _FakeSink(rt)
        await _handle_idle_prompt(rt, _FakeResources(), sink)
        assert rt.idle_prompted is True
        assert len(sink.audio_chunks) == 1

    @pytest.mark.asyncio
    async def test_does_not_fire_twice_in_the_same_visit(self) -> None:
        rt = _runtime(S.idle)
        rt.idle_prompted = True
        sink = _FakeSink(rt)
        await _handle_idle_prompt(rt, _FakeResources(), sink)
        assert sink.audio_chunks == []

    @pytest.mark.asyncio
    async def test_missing_clip_still_sets_the_flag_without_crashing(self) -> None:
        rt = _runtime(S.idle)
        sink = _FakeSink(rt)
        await _handle_idle_prompt(rt, _FakeResources(has_idle_prompt=False), sink)
        assert rt.idle_prompted is True
        assert sink.audio_chunks == []


class TestIdleAbandon:
    @pytest.mark.asyncio
    async def test_calls_the_abandon_callback(self) -> None:
        rt = _runtime(S.idle)
        called = []

        async def _on_abandon() -> None:
            called.append(True)

        await _handle_idle_abandon(rt, _on_abandon)
        assert called == [True]


class TestEndpointingTimeout:
    @pytest.mark.asyncio
    async def test_degrades_then_returns_to_listening(self) -> None:
        """Task 2.1's degraded table: no ASR/TTS/persona component failed here — the cascade
        itself stalled — so `component == "transport"`, and the session must be able to keep
        listening afterward, not get stuck."""
        rt = _runtime(S.endpointing)
        sink = _FakeSink(rt)
        await _handle_endpointing_timeout(rt, sink)
        assert sink.degraded_calls == [("transport", "Endpoint decision took too long.", True)]
        assert rt.state_machine.state is S.listening


class TestThinkingTimeout:
    @pytest.mark.asyncio
    async def test_first_timeout_degrades_to_idle_without_forcing_local_model(self) -> None:
        rt = _runtime(S.thinking)
        sink = _FakeSink(rt)
        await _handle_thinking_timeout(rt, sink)
        assert sink.degraded_calls == [
            ("persona", "The persona model took too long to respond.", True)
        ]
        assert rt.state_machine.state is S.idle
        assert rt.thinking_retry_used is True
        assert rt.persona_use_local_for_remainder is False  # Task 2.1: "retry once" first

    @pytest.mark.asyncio
    async def test_second_timeout_in_the_session_switches_to_local_model(self) -> None:
        """Task 2.1's degraded table: "Persona model 429 / error -> switch to
        MODEL_PERSONA_LOCAL for the remainder of the session." Modeled here as "the retry
        already happened once and it timed out again."""
        rt = _runtime(S.thinking)
        rt.thinking_retry_used = True  # simulates an earlier timeout this session
        sink = _FakeSink(rt)
        await _handle_thinking_timeout(rt, sink)
        assert rt.persona_use_local_for_remainder is True

    @pytest.mark.asyncio
    async def test_cancels_the_in_flight_turn_task(self) -> None:
        rt = _runtime(S.thinking)
        started = asyncio.Event()

        async def _hang_forever() -> None:
            started.set()
            await asyncio.sleep(1000)

        rt.speaking_task = asyncio.create_task(_hang_forever())
        await started.wait()
        sink = _FakeSink(rt)
        await _handle_thinking_timeout(rt, sink)
        assert rt.speaking_task.cancelled() or rt.speaking_task.done()


class TestSpeakingTimeout:
    @pytest.mark.asyncio
    async def test_degrades_to_idle_and_cancels_the_turn_task(self) -> None:
        rt = _runtime(S.speaking)
        sink = _FakeSink(rt)
        await _handle_speaking_timeout(rt, sink)
        assert sink.degraded_calls == [("tts", "Playback stalled.", True)]
        assert rt.state_machine.state is S.idle


class TestRunStateWatchdogEndToEnd:
    """A couple of full poll-loop runs (fast poll interval, no real multi-second sleeps) to
    prove the watchdog itself — not just the handler functions — actually detects and acts on
    an expired state. This is the "wired up for real" half of "every state has a timeout with a
    test that forces expiry"; the exhaustive per-state math is test_state_machine.py's job."""

    @pytest.mark.asyncio
    async def test_thinking_timeout_fires_through_the_real_poll_loop(self) -> None:
        rt = _runtime(S.thinking)
        fake_now = [1000.0]
        rt.state_machine.clock = lambda: fake_now[0]
        rt.state_machine.entered_at = 0.0  # already "STATE_TIMEOUT_MS[S.thinking]+" in the past
        sink = _FakeSink(rt)

        async def _never_abandon() -> None:
            raise AssertionError("idle abandon should never fire for a thinking-state test")

        async def _never_distress() -> None:
            raise AssertionError("distress exit should never fire for a thinking-state test")

        task = asyncio.create_task(
            run_state_watchdog(
                rt,
                _FakeResources(),
                sink,
                on_idle_abandon=_never_abandon,
                on_distress_exit=_never_distress,
                poll_interval_s=0.01,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert rt.state_machine.state is S.idle  # thinking -> degraded -> idle already happened
        assert sink.degraded_calls

    @pytest.mark.asyncio
    async def test_idle_abandon_fires_through_the_real_poll_loop(self) -> None:
        rt = _runtime(S.idle)
        rt.idle_accumulated_ms = 119_999.0  # one poll tick away from the 120s ceiling
        sink = _FakeSink(rt)
        abandoned = asyncio.Event()

        async def _on_abandon() -> None:
            abandoned.set()

        async def _never_distress() -> None:
            raise AssertionError("distress exit should never fire for an idle-abandon test")

        task = asyncio.create_task(
            run_state_watchdog(
                rt,
                _FakeResources(),
                sink,
                on_idle_abandon=_on_abandon,
                on_distress_exit=_never_distress,
                poll_interval_s=0.01,
            )
        )
        await asyncio.wait_for(abandoned.wait(), timeout=2.0)
        # The watchdog returns on its own once idle-abandon fires (Task 2.1: "the session is
        # ending — nothing left for this watchdog to supervise") — no cancellation needed here,
        # unlike the thinking-timeout test above where the loop keeps polling.
        await asyncio.wait_for(task, timeout=1.0)

    @pytest.mark.asyncio
    async def test_distress_exit_fires_through_the_real_poll_loop(self) -> None:
        # Task 2.6 (AS-07): checked ahead of the normal `idle` handling, so a session sitting in
        # `idle` for this reason is closed immediately rather than treated as an ordinary quiet
        # moment (no idle-prompt nudge, no accumulating toward the 120s abandon ceiling first).
        rt = _runtime(S.idle)
        rt.distress_exit_pending = True
        sink = _FakeSink(rt)
        exited = asyncio.Event()

        async def _never_abandon() -> None:
            raise AssertionError("idle abandon should never fire once distress_exit_pending is set")

        async def _on_distress() -> None:
            exited.set()

        task = asyncio.create_task(
            run_state_watchdog(
                rt,
                _FakeResources(),
                sink,
                on_idle_abandon=_never_abandon,
                on_distress_exit=_on_distress,
                poll_interval_s=0.01,
            )
        )
        await asyncio.wait_for(exited.wait(), timeout=2.0)
        await asyncio.wait_for(task, timeout=1.0)
