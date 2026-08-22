# GENERATED — DO NOT EDIT. Run `make schema`.
#
# Source: packages/schema/ws-messages.schema.json
# Generator: packages/schema/generate.py -> datamodel-code-generator

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Seq(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description="Monotonic uint32, per direction (client and server each keep their own counter).",
            ge=0,
            le=4294967295,
        ),
    ]


class ServerMachineState(StrEnum):
    connecting = "connecting"
    idle = "idle"
    listening = "listening"
    endpointing = "endpointing"
    thinking = "thinking"
    speaking = "speaking"
    interrupted = "interrupted"
    closing = "closing"
    degraded = "degraded"
    closed = "closed"


class ClientState(StrEnum):
    your_turn = "your_turn"
    thinking = "thinking"
    speaking = "speaking"
    connection_trouble = "connection_trouble"
    ended = "ended"


class WordTiming(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    word: str
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]


class Stage(StrEnum):
    endpoint_detect = "endpoint_detect"
    asr_finalize = "asr_finalize"
    prompt_assemble = "prompt_assemble"
    model_ttft = "model_ttft"
    first_chunk_assemble = "first_chunk_assemble"
    tts_first_chunk = "tts_first_chunk"
    transport = "transport"
    e2e = "e2e"


class LatencyStage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    stage: Annotated[Stage, Field(description="Fixed enum — CLAUDE.md §8.")]
    duration_ms: Annotated[float, Field(ge=0.0)]


class Hello(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["hello"]
    seq: Seq
    protocol_version: Annotated[
        str,
        Field(
            description='e.g. "1.0". Mismatched major version -> error ORCHESTRATION_PROTOCOL_MISMATCH, fatal.'
        ),
    ]
    session_id: UUID
    client_sample_rate: Annotated[int, Field(ge=1)]
    client_frame_ms: Annotated[int, Field(ge=1)]
    capabilities: list[str]


class Resume(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["resume"]
    seq: Seq
    protocol_version: str
    session_id: UUID
    last_server_seq: Seq
    last_client_seq: Seq


class Mute(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["mute"]
    seq: Seq
    muted: bool


class Reason(StrEnum):
    user_hangup = "user_hangup"
    user_abandoned = "user_abandoned"


class EndSession(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["end_session"]
    seq: Seq
    reason: Reason


class Ping(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["ping"]
    seq: Seq
    client_time_ms: Annotated[int, Field(ge=0)]


class Ready(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["ready"]
    seq: Seq
    session_id: UUID
    server_sample_rate: Annotated[int, Field(ge=1)]
    protocol_version: str
    resumed: bool


class StateChange(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["state_change"]
    seq: Seq
    state: ServerMachineState
    client_state: ClientState
    at_ms: Annotated[int, Field(ge=0)]


class PartialTranscript(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["partial_transcript"]
    seq: Seq
    turn_index: Annotated[int, Field(ge=0)]
    text: str
    stability: Annotated[float, Field(ge=0.0, le=1.0)]
    at_ms: Annotated[int, Field(ge=0)]


class TurnFinalized(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["turn_finalized"]
    seq: Seq
    turn_id: UUID
    turn_index: Annotated[int, Field(ge=0)]
    text: str
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0)]
    asr_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    word_timings: list[WordTiming]


class PersonaText(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["persona_text"]
    seq: Seq
    turn_id: UUID
    text_delta: str
    done: bool


class AudioChunkMeta(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["audio_chunk_meta"]
    seq: Seq
    turn_id: UUID
    chunk_seq: Annotated[int, Field(ge=0)]
    sample_rate: Annotated[int, Field(ge=1)]
    byte_length: Annotated[int, Field(ge=0)]
    is_final: bool


class Interrupted(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["interrupted"]
    seq: Seq
    turn_id: UUID
    at_ms: Annotated[int, Field(ge=0)]
    truncated_text: str


class Component(StrEnum):
    asr = "asr"
    tts = "tts"
    persona = "persona"
    transport = "transport"


class Degraded(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["degraded"]
    seq: Seq
    component: Component
    message: str
    recoverable: bool


class LatencyReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["latency_report"]
    seq: Seq
    turn_id: UUID
    stages: list[LatencyStage]
    e2e_ms: Annotated[float, Field(ge=0.0)]


class SessionClosed(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["session_closed"]
    seq: Seq
    reason: str
    duration_ms: Annotated[int, Field(ge=0)]
    report_pending: bool


class WsError(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["error"]
    seq: Seq
    code: str
    message: str
    recovery: str
    fatal: bool
    trace_id: str


class Pong(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["pong"]
    seq: Seq
    client_time_ms: Annotated[int, Field(ge=0)]
    server_time_ms: Annotated[int, Field(ge=0)]


class WsEnvelope(
    RootModel[
        Hello
        | Resume
        | Mute
        | EndSession
        | Ping
        | Ready
        | StateChange
        | PartialTranscript
        | TurnFinalized
        | PersonaText
        | AudioChunkMeta
        | Interrupted
        | Degraded
        | LatencyReport
        | SessionClosed
        | WsError
        | Pong
    ]
):
    root: Annotated[
        Hello
        | Resume
        | Mute
        | EndSession
        | Ping
        | Ready
        | StateChange
        | PartialTranscript
        | TurnFinalized
        | PersonaText
        | AudioChunkMeta
        | Interrupted
        | Degraded
        | LatencyReport
        | SessionClosed
        | WsError
        | Pong,
        Field(
            description="GENERATED SOURCE OF TRUTH — see CLAUDE.md §1.3 and docs/phase-0-BUILD.md TASK 0.3. Changing this file is a versioned protocol migration, not a refactor. Run `make schema` after any edit.",
            discriminator="type",
            title="InteractAI WebSocket Messages",
        ),
    ]
