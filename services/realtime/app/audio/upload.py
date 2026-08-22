"""Uploads the user's recording to S3/MinIO (Task 1.1/2.2c). Only the *user's* audio is ever
uploaded — CLAUDE.md §1.8: "Never store persona audio. It is regenerable from transcript + voice
id" — this module has no persona-audio path at all, on purpose.

Task 2.2c's "multipart upload, one part per ~30s" is implemented as periodic whole-object
checkpoint re-uploads instead of true S3 multipart — see
docs/decisions/0009-incremental-upload-and-opus.md for why (part-size minimums, and an
incomplete multipart upload isn't actually a "playable partial recording"). Finalize transcodes
to Opus at 24kbps (Task 2.2c) and deletes the WAV object + local PCM, superseding
docs/decisions/0007's Phase 1 upload-once-at-finalize simplification.

The key convention (`users/{user_id}/sessions/{session_id}.<ext>`) matches
`services/api/app/services/user_service.py`'s `delete_prefix(f"users/{user_id}/")` call, so
deleting a user's account purges recordings without this module needing its own deletion logic.
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid as std_uuid
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any

import av
import boto3

from ..core.config import get_settings
from ..core.logging import get_logger
from .protocol import UPSTREAM_CHANNELS, UPSTREAM_SAMPLE_RATE

logger = get_logger(__name__)

WAV_HEADER_BYTES = 44
OPUS_BITRATE = 24_000  # 24kbps, Task 2.2c


@lru_cache
def get_s3_client() -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=boto3.session.Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
        ),
    )


def recording_key_wav(user_id: std_uuid.UUID, session_id: std_uuid.UUID) -> str:
    return f"users/{user_id}/sessions/{session_id}.wav"


def recording_key_opus(user_id: std_uuid.UUID, session_id: std_uuid.UUID) -> str:
    return f"users/{user_id}/sessions/{session_id}.opus"


# ── Pure functions (no S3, no filesystem beyond the given path) — the actual transcoding logic,
# testable without any object storage at all. ────────────────────────────────────────────────


def read_pcm_prefix(path: Path) -> bytes:
    """Reads whatever complete PCM bytes are on disk right now, via a fresh read-only handle —
    the write handle `SessionWavWriter` holds open (Task 1.2c) is never touched, so this never
    contends with or disturbs live ingest. `os.path.getsize` is read first so a frame appended
    concurrently after that snapshot simply isn't included this time; it will be in the next
    checkpoint."""
    if not path.exists():
        return b""
    size = os.path.getsize(path)
    if size <= WAV_HEADER_BYTES:
        return b""
    with path.open("rb") as f:
        f.seek(WAV_HEADER_BYTES)
        return f.read(size - WAV_HEADER_BYTES)


def pcm_to_wav_bytes(
    pcm: bytes, *, sample_rate: int = UPSTREAM_SAMPLE_RATE, channels: int = UPSTREAM_CHANNELS
) -> bytes:
    """Wraps raw PCM16 in a fresh, correctly-headered WAV — unlike the file on disk mid-write,
    this is always a complete, valid, playable object the instant it's built."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


OPUS_ENCODE_RATE = 48_000  # libopus's native rate; anything else is resampled up to it


def encode_wav_to_opus_bytes(wav_bytes: bytes, *, bitrate: int = OPUS_BITRATE) -> bytes:
    """Task 2.2c: re-encode to Opus at 24kbps. PyAV (`av`) wraps libav/ffmpeg, which this
    machine's ffmpeg build has `libopus` support for — no extra dependency needed beyond what
    `services/realtime` already declares.

    Two things that are easy to get wrong here, verified by direct measurement rather than
    assumed:
      1. **Explicit resampling to 48kHz is required**, not optional — libopus only accepts
         8/12/16/24/48kHz internally, and feeding it 16kHz frames without resampling first
         produces a file whose header claims 48kHz for 16kHz-rate audio (wrong pitch/speed).
      2. **`vbr=off` (CBR), not the encoder's default VBR, is what actually hits "24kbps".**
         Measured against a 10s fixture: default VBR produced ~39kbps (a ~6.5x reduction from
         WAV, short of Task 2.2c's "≥10x" target); CBR produced ~24.8kbps (~10.3x) — VBR's
         average-bitrate *target* is not a ceiling, and this codec quietly used meaningfully
         more than the requested nominal rate for this content.
    """
    src = io.BytesIO(wav_bytes)
    dst = io.BytesIO()
    with (
        av.open(src, mode="r") as in_container,
        av.open(dst, mode="w", format="ogg") as out_container,
    ):
        in_stream = in_container.streams.audio[0]
        out_stream = out_container.add_stream(
            "libopus", rate=OPUS_ENCODE_RATE, options={"vbr": "off"}
        )
        out_stream.bit_rate = bitrate
        resampler = av.AudioResampler(format="s16", layout="mono", rate=OPUS_ENCODE_RATE)
        for frame in in_container.decode(in_stream):
            for resampled in resampler.resample(frame):
                for packet in out_stream.encode(resampled):
                    out_container.mux(packet)
        for packet in out_stream.encode(None):  # flush
            out_container.mux(packet)
    return dst.getvalue()


# ── S3-touching wrappers ────────────────────────────────────────────────────────────────────


def _put_bytes_sync(data: bytes, bucket: str, key: str, content_type: str) -> None:
    get_s3_client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def _delete_sync(bucket: str, key: str) -> None:
    get_s3_client().delete_object(Bucket=bucket, Key=key)


async def checkpoint_upload(
    path: Path, *, user_id: std_uuid.UUID, session_id: std_uuid.UUID
) -> str | None:
    """Task 2.2c: "Audio uploads to object storage as the session runs, not at the end." Called
    periodically during a live session and once more at finalize before the Opus transcode.
    Returns the object key on success, or `None` if storage isn't configured or the upload
    failed — a missing checkpoint must never break the turn path or fail finalisation; the local
    file (Task 1.2c's incremental write) is still the durable source of truth until this
    succeeds."""
    settings = get_settings()
    if not settings.s3_bucket:
        return None
    pcm = await asyncio.to_thread(read_pcm_prefix, path)
    if not pcm:
        return None
    wav_bytes = pcm_to_wav_bytes(pcm)
    key = recording_key_wav(user_id, session_id)
    try:
        await asyncio.to_thread(_put_bytes_sync, wav_bytes, settings.s3_bucket, key, "audio/wav")
    except Exception:
        logger.warning("recording_checkpoint_failed", session_id=str(session_id), key=key)
        return None
    return key


async def finalize_recording(
    path: Path, *, user_id: std_uuid.UUID, session_id: std_uuid.UUID
) -> str | None:
    """Task 2.2c: final checkpoint, transcode to Opus, delete the WAV object and the local PCM.
    Returns the Opus object key, or `None` if storage isn't configured. The local WAV file is
    deleted only once the Opus upload has actually succeeded — losing the recording entirely is
    worse than leaving a stray local file for the next process restart to find."""
    settings = get_settings()
    if not settings.s3_bucket:
        return None

    wav_key = await checkpoint_upload(path, user_id=user_id, session_id=session_id)
    pcm = await asyncio.to_thread(read_pcm_prefix, path)
    if not pcm:
        return wav_key  # nothing was ever recorded — no turn happened; nothing to transcode

    wav_bytes = pcm_to_wav_bytes(pcm)
    try:
        opus_bytes = await asyncio.to_thread(encode_wav_to_opus_bytes, wav_bytes)
        opus_key = recording_key_opus(user_id, session_id)
        await asyncio.to_thread(
            _put_bytes_sync, opus_bytes, settings.s3_bucket, opus_key, "audio/ogg"
        )
    except Exception:
        logger.warning("recording_opus_transcode_failed", session_id=str(session_id))
        return wav_key  # the WAV checkpoint above is still a valid, playable fallback

    if wav_key is not None:
        try:
            await asyncio.to_thread(_delete_sync, settings.s3_bucket, wav_key)
        except Exception:
            logger.warning("recording_wav_cleanup_failed", session_id=str(session_id), key=wav_key)

    try:
        await asyncio.to_thread(path.unlink)
    except OSError:
        logger.warning("recording_local_cleanup_failed", session_id=str(session_id), path=str(path))

    return opus_key
