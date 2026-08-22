"""The binary frame format — FROZEN as of Task 1.2d. See docs/03-realtime-protocol.md.

    offset  size  field
    0       1     version        uint8, currently 1
    1       1     kind           uint8: 1 = mic PCM up, 2 = TTS audio down
    2       2     reserved       uint16, zero
    4       4     seq            uint32 big-endian, monotonic per direction
    8       4     timestamp_ms   uint32 big-endian, relative to session start
    12      n     payload        Int16 PCM little-endian

Changing any constant in this file after the freeze is a versioned protocol migration (bump
PROTOCOL_VERSION and negotiate in `hello`/`ready`), not a refactor — CLAUDE.md §1.3.
tests/unit/realtime/test_protocol_frozen.py asserts these values never drift silently.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

PROTOCOL_VERSION = 1

FRAME_KIND_MIC_UP = 1
FRAME_KIND_TTS_DOWN = 2

# Upstream (browser/CLI -> server): fixed contract, matches AUDIO_* in .env.example exactly.
UPSTREAM_SAMPLE_RATE = 16_000
UPSTREAM_FRAME_MS = 20
UPSTREAM_FRAME_SAMPLES = 320  # 20ms @ 16kHz
UPSTREAM_PAYLOAD_BYTES = UPSTREAM_FRAME_SAMPLES * 2  # Int16 = 2 bytes/sample -> 640
UPSTREAM_CHANNELS = 1

# Downstream (server -> browser/CLI): a single fixed rate, resampled server-side (Task 1.5b).
DOWNSTREAM_SAMPLE_RATE = 24_000

_HEADER_FORMAT = ">BBHII"  # version, kind, reserved, seq, timestamp_ms — all big-endian
HEADER_BYTES = struct.calcsize(_HEADER_FORMAT)  # 12
UPSTREAM_FRAME_BYTES = HEADER_BYTES + UPSTREAM_PAYLOAD_BYTES  # 652

_SEQ_MAX = 2**32 - 1
_TIMESTAMP_MAX = 2**32 - 1


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    version: int
    kind: int
    seq: int
    timestamp_ms: int
    payload: bytes


class FrameDecodeError(ValueError):
    """Malformed header or truncated payload. Callers map this to CAPTURE_FRAME_MALFORMED and
    drop the frame — never close the socket for one bad frame (Task 1.2c)."""


def encode_frame(*, kind: int, seq: int, timestamp_ms: int, payload: bytes) -> bytes:
    if not (0 <= seq <= _SEQ_MAX):
        raise ValueError(f"seq out of range: {seq}")
    if not (0 <= timestamp_ms <= _TIMESTAMP_MAX):
        raise ValueError(f"timestamp_ms out of range: {timestamp_ms}")
    header = struct.pack(_HEADER_FORMAT, PROTOCOL_VERSION, kind, 0, seq, timestamp_ms)
    return header + payload


def decode_frame(data: bytes) -> DecodedFrame:
    if len(data) < HEADER_BYTES:
        raise FrameDecodeError(f"frame shorter than header: {len(data)} bytes")
    version, kind, _reserved, seq, timestamp_ms = struct.unpack(_HEADER_FORMAT, data[:HEADER_BYTES])
    return DecodedFrame(
        version=version, kind=kind, seq=seq, timestamp_ms=timestamp_ms, payload=data[HEADER_BYTES:]
    )


def validate_upstream_frame(data: bytes) -> DecodedFrame:
    """Task 1.2c: upstream must be exactly UPSTREAM_FRAME_BYTES (652). Anything else raises
    FrameDecodeError — the caller drops the single frame and keeps the socket open."""
    if len(data) != UPSTREAM_FRAME_BYTES:
        raise FrameDecodeError(f"expected {UPSTREAM_FRAME_BYTES} bytes, got {len(data)}")
    frame = decode_frame(data)
    if frame.version != PROTOCOL_VERSION:
        raise FrameDecodeError(f"unsupported protocol version {frame.version}")
    if frame.kind != FRAME_KIND_MIC_UP:
        raise FrameDecodeError(f"expected kind={FRAME_KIND_MIC_UP} (mic up), got {frame.kind}")
    if len(frame.payload) != UPSTREAM_PAYLOAD_BYTES:
        raise FrameDecodeError(
            f"expected {UPSTREAM_PAYLOAD_BYTES}-byte payload, got {len(frame.payload)}"
        )
    return frame


def pcm16le_to_samples(payload: bytes) -> list[int]:
    """Decode an Int16 little-endian payload to a list of sample values. Used by tests and the
    WAV writer; the hot ingest path stays on `bytes`/numpy, not Python lists."""
    count = len(payload) // 2
    return list(struct.unpack(f"<{count}h", payload))
