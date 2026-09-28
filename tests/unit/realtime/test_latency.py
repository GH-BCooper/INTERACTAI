"""Task 1.6a acceptance: no sampling, batched fire-and-forget writes, flush on close."""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from services.realtime.app.metrics.latency import FLUSH_BATCH_SIZE, LatencyRecorder, stage
from services.realtime.app.metrics.model_calls import ModelCallRecord, record_model_call
from services.realtime.app.schemas.ws import Stage


class FakeWriter:
    def __init__(self) -> None:
        self.batches: list[list[dict]] = []

    async def __call__(self, rows: list[dict]) -> None:
        self.batches.append(rows)


@pytest.mark.asyncio
async def test_stage_records_a_row_with_measured_duration() -> None:
    writer = FakeWriter()
    recorder = LatencyRecorder(writer)
    session_id, turn_id = uuid.uuid4(), uuid.uuid4()

    # Timed against the same clock `stage` uses, rather than asserting the row is >= the
    # *nominal* sleep. `asyncio.sleep(0.01)` is a floor on the event loop's timer, not on
    # `perf_counter`, and on Windows the two disagree by more than the interval: this assertion
    # read `>= 10.0` until 2026-09-28 and failed intermittently under full-suite load at 6.26ms.
    # What the recorder owes us is that it measures the block it wrapped — not that asyncio's
    # timer is accurate, which is not this project's code and not this test's subject.
    started = time.perf_counter()
    async with stage(recorder, session_id, turn_id, Stage.model_ttft):
        await asyncio.sleep(0.01)
    elapsed_ms = (time.perf_counter() - started) * 1000

    await recorder.flush()
    assert len(writer.batches) == 1
    row = writer.batches[0][0]
    assert row["session_id"] == session_id
    assert row["turn_id"] == turn_id
    assert row["stage"] == "model_ttft"
    assert row["duration_ms"] > 0
    # Bounded above by the outer measurement, and within a millisecond of it below: anything
    # wider would also pass for a recorder that timed the wrong thing.
    assert row["duration_ms"] <= elapsed_ms
    assert row["duration_ms"] >= elapsed_ms - 1.0


@pytest.mark.asyncio
async def test_every_call_records_no_sampling() -> None:
    writer = FakeWriter()
    recorder = LatencyRecorder(writer)
    sid, tid = uuid.uuid4(), uuid.uuid4()

    for _ in range(7):
        async with stage(recorder, sid, tid, Stage.transport):
            pass

    await recorder.flush()
    total_rows = sum(len(b) for b in writer.batches)
    assert total_rows == 7


@pytest.mark.asyncio
async def test_flushes_automatically_at_batch_size() -> None:
    writer = FakeWriter()
    recorder = LatencyRecorder(writer)
    sid, tid = uuid.uuid4(), uuid.uuid4()

    for _ in range(FLUSH_BATCH_SIZE):
        recorder.record(sid, tid, Stage.e2e, 100.0)

    # record() fires the flush as a background task; give the loop a tick to run it.
    await asyncio.sleep(0)
    await recorder.stop()

    total_rows = sum(len(b) for b in writer.batches)
    assert total_rows == FLUSH_BATCH_SIZE


@pytest.mark.asyncio
async def test_flush_on_stop_captures_a_partial_batch() -> None:
    writer = FakeWriter()
    recorder = LatencyRecorder(writer)
    sid, tid = uuid.uuid4(), uuid.uuid4()

    recorder.record(sid, tid, Stage.endpoint_detect, 42.0)
    recorder.record(sid, tid, Stage.asr_finalize, 90.0)
    await recorder.stop()

    total_rows = sum(len(b) for b in writer.batches)
    assert total_rows == 2


@pytest.mark.asyncio
async def test_flush_is_a_noop_on_an_empty_buffer() -> None:
    writer = FakeWriter()
    recorder = LatencyRecorder(writer)
    await recorder.flush()
    assert writer.batches == []


@pytest.mark.asyncio
async def test_periodic_flush_fires_on_its_own_schedule() -> None:
    writer = FakeWriter()
    recorder = LatencyRecorder(writer, flush_interval_s=0.02)
    sid, tid = uuid.uuid4(), uuid.uuid4()
    recorder.record(sid, tid, Stage.prompt_assemble, 5.0)

    await recorder.start_periodic_flush()
    await asyncio.sleep(0.05)
    await recorder.stop()

    total_rows = sum(len(b) for b in writer.batches)
    assert total_rows == 1


@pytest.mark.asyncio
async def test_stage_metadata_does_not_appear_in_the_db_row() -> None:
    """docs/decisions/0005: metadata is logged, never written to latency_events."""
    writer = FakeWriter()
    recorder = LatencyRecorder(writer)
    sid, tid = uuid.uuid4(), uuid.uuid4()

    async with stage(recorder, sid, tid, Stage.asr_finalize, rtf=0.42):
        pass

    await recorder.flush()
    row = writer.batches[0][0]
    assert set(row.keys()) == {"session_id", "turn_id", "stage", "duration_ms"}


@pytest.mark.asyncio
async def test_record_model_call_writes_every_field() -> None:
    calls: list[dict] = []

    async def fake_writer(**kwargs: object) -> None:
        calls.append(kwargs)

    record = ModelCallRecord(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        role="persona",
        model="groq/openai/gpt-oss-20b",
        prompt_version="1.0",
        tokens_in=120,
        tokens_out=48,
        ttft_ms=210.5,
        total_latency_ms=640.0,
        cost_cents=0.03,
        cached=False,
    )
    await record_model_call(fake_writer, record)

    assert len(calls) == 1
    call = calls[0]
    assert call["role"] == "persona"
    assert call["tokens_in"] == 120
    assert call["tokens_out"] == 48
    assert call["ttft_ms"] == 210.5
    assert "call_id" in call  # generated fresh, not caller-supplied
