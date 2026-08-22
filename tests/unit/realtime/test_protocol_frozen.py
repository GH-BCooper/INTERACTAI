"""Task 1.2d: the binary frame format is frozen. This test is the CI guard against silent
drift — a change to any constant here must be a deliberate, versioned migration."""

from __future__ import annotations

import pytest

from services.realtime.app.audio import protocol as p


def test_frozen_constants() -> None:
    assert p.PROTOCOL_VERSION == 1
    assert p.FRAME_KIND_MIC_UP == 1
    assert p.FRAME_KIND_TTS_DOWN == 2
    assert p.UPSTREAM_SAMPLE_RATE == 16_000
    assert p.UPSTREAM_FRAME_MS == 20
    assert p.UPSTREAM_FRAME_SAMPLES == 320
    assert p.UPSTREAM_PAYLOAD_BYTES == 640
    assert p.UPSTREAM_CHANNELS == 1
    assert p.DOWNSTREAM_SAMPLE_RATE == 24_000
    assert p.HEADER_BYTES == 12
    assert p.UPSTREAM_FRAME_BYTES == 652


def test_encode_decode_round_trip() -> None:
    payload = bytes(range(256)) * 2 + bytes(128)  # arbitrary 640 bytes
    assert len(payload) == 640
    frame = p.encode_frame(kind=p.FRAME_KIND_MIC_UP, seq=42, timestamp_ms=1234, payload=payload)
    assert len(frame) == p.UPSTREAM_FRAME_BYTES

    decoded = p.decode_frame(frame)
    assert decoded.version == p.PROTOCOL_VERSION
    assert decoded.kind == p.FRAME_KIND_MIC_UP
    assert decoded.seq == 42
    assert decoded.timestamp_ms == 1234
    assert decoded.payload == payload


def test_header_is_big_endian() -> None:
    frame = p.encode_frame(kind=p.FRAME_KIND_MIC_UP, seq=1, timestamp_ms=0, payload=b"\x00" * 640)
    # seq=1 big-endian uint32 -> bytes 4-7 are 00 00 00 01
    assert frame[4:8] == b"\x00\x00\x00\x01"


@pytest.mark.parametrize("bad_length", [0, 1, 11, 651, 653, 1000])
def test_validate_rejects_wrong_length(bad_length: int) -> None:
    with pytest.raises(p.FrameDecodeError):
        p.validate_upstream_frame(b"\x00" * bad_length)


def test_validate_rejects_wrong_kind() -> None:
    frame = p.encode_frame(kind=p.FRAME_KIND_TTS_DOWN, seq=0, timestamp_ms=0, payload=b"\x00" * 640)
    with pytest.raises(p.FrameDecodeError):
        p.validate_upstream_frame(frame)


def test_validate_rejects_wrong_version() -> None:
    frame = p.encode_frame(kind=p.FRAME_KIND_MIC_UP, seq=0, timestamp_ms=0, payload=b"\x00" * 640)
    tampered = bytes([99]) + frame[1:]
    with pytest.raises(p.FrameDecodeError):
        p.validate_upstream_frame(tampered)


def test_validate_accepts_well_formed_frame() -> None:
    frame = p.encode_frame(
        kind=p.FRAME_KIND_MIC_UP, seq=7, timestamp_ms=140, payload=b"\x01\x02" * 320
    )
    decoded = p.validate_upstream_frame(frame)
    assert decoded.seq == 7
    assert decoded.timestamp_ms == 140


def test_pcm16le_round_trip() -> None:
    import struct

    samples = [-32768, -1, 0, 1, 32767]
    payload = struct.pack(f"<{len(samples)}h", *samples)
    assert p.pcm16le_to_samples(payload) == samples


@pytest.mark.parametrize("seq", [0, 2**32 - 1])
def test_seq_boundary_values_are_valid(seq: int) -> None:
    p.encode_frame(kind=p.FRAME_KIND_MIC_UP, seq=seq, timestamp_ms=0, payload=b"\x00" * 640)


def test_seq_out_of_range_rejected() -> None:
    with pytest.raises(ValueError):
        p.encode_frame(kind=p.FRAME_KIND_MIC_UP, seq=2**32, timestamp_ms=0, payload=b"\x00" * 640)
