"""Round-trips one instance of every WsMessage variant through the generated Pydantic models.

See docs/phase-0-BUILD.md TASK 0.3 acceptance criteria. Also asserts additionalProperties:false
and unknown-`type` rejection, since those are the properties the whole codegen exercise exists
to guarantee.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.realtime.app.schemas import ws

UUID = "11111111-1111-1111-1111-111111111111"

SAMPLES: dict[str, dict] = {
    "hello": {
        "type": "hello",
        "seq": 1,
        "protocol_version": "1.0",
        "session_id": UUID,
        "client_sample_rate": 16000,
        "client_frame_ms": 20,
        "capabilities": [],
    },
    "resume": {
        "type": "resume",
        "seq": 1,
        "protocol_version": "1.0",
        "session_id": UUID,
        "last_server_seq": 0,
        "last_client_seq": 0,
    },
    "mute": {"type": "mute", "seq": 1, "muted": True},
    "end_session": {"type": "end_session", "seq": 1, "reason": "user_hangup"},
    "ping": {"type": "ping", "seq": 1, "client_time_ms": 0},
    "ready": {
        "type": "ready",
        "seq": 1,
        "session_id": UUID,
        "server_sample_rate": 16000,
        "protocol_version": "1.0",
        "resumed": False,
    },
    "state_change": {
        "type": "state_change",
        "seq": 1,
        "state": "listening",
        "client_state": "your_turn",
        "at_ms": 0,
    },
    "partial_transcript": {
        "type": "partial_transcript",
        "seq": 1,
        "turn_index": 0,
        "text": "hi",
        "stability": 0.5,
        "at_ms": 0,
    },
    "turn_finalized": {
        "type": "turn_finalized",
        "seq": 1,
        "turn_id": UUID,
        "turn_index": 0,
        "text": "hi",
        "start_ms": 0,
        "end_ms": 100,
        "asr_confidence": 0.9,
        "word_timings": [{"word": "hi", "start_ms": 0, "end_ms": 100}],
    },
    "persona_text": {
        "type": "persona_text",
        "seq": 1,
        "turn_id": UUID,
        "text_delta": "hi",
        "done": False,
    },
    "audio_chunk_meta": {
        "type": "audio_chunk_meta",
        "seq": 1,
        "turn_id": UUID,
        "chunk_seq": 0,
        "sample_rate": 22050,
        "byte_length": 640,
        "is_final": False,
    },
    "interrupted": {
        "type": "interrupted",
        "seq": 1,
        "turn_id": UUID,
        "at_ms": 0,
        "truncated_text": "hi",
    },
    "degraded": {
        "type": "degraded",
        "seq": 1,
        "component": "tts",
        "message": "holding line",
        "recoverable": True,
    },
    "latency_report": {
        "type": "latency_report",
        "seq": 1,
        "turn_id": UUID,
        "stages": [{"stage": "e2e", "duration_ms": 1200.0}],
        "e2e_ms": 1200.0,
    },
    "session_closed": {
        "type": "session_closed",
        "seq": 1,
        "reason": "user_hangup",
        "duration_ms": 1000,
        "report_pending": True,
    },
    "error": {
        "type": "error",
        "seq": 1,
        "code": "ORCHESTRATION_PROTOCOL_MISMATCH",
        "message": "bad version",
        "recovery": "reconnect",
        "fatal": True,
        "trace_id": "abc",
    },
    "pong": {"type": "pong", "seq": 1, "client_time_ms": 0, "server_time_ms": 0},
}


def test_every_message_type_has_a_sample() -> None:
    # The 17 types listed in docs/phase-0-BUILD.md TASK 0.3.
    assert len(SAMPLES) == 17


@pytest.mark.parametrize("type_name", sorted(SAMPLES))
def test_round_trip(type_name: str) -> None:
    payload = SAMPLES[type_name]
    envelope = ws.WsEnvelope.model_validate(payload)
    assert envelope.root.type == type_name

    dumped = envelope.model_dump(mode="json")
    re_parsed = ws.WsEnvelope.model_validate(dumped)
    assert re_parsed.root.type == type_name


@pytest.mark.parametrize("type_name", sorted(SAMPLES))
def test_additional_properties_rejected(type_name: str) -> None:
    payload = {**SAMPLES[type_name], "unexpected_field": "nope"}
    with pytest.raises(ValidationError):
        ws.WsEnvelope.model_validate(payload)


def test_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ws.WsEnvelope.model_validate({"type": "not_a_real_message", "seq": 1})


def test_protocol_version_is_not_hardcoded_to_current() -> None:
    # protocol_version is a free string at the schema layer — mismatch handling (error
    # ORCHESTRATION_PROTOCOL_MISMATCH) is realtime application logic, not a schema constraint.
    envelope = ws.WsEnvelope.model_validate({**SAMPLES["hello"], "protocol_version": "99.0"})
    assert envelope.root.protocol_version == "99.0"
