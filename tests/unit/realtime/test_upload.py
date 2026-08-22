"""Task 1.1/2.2c: recording upload, checkpointing and Opus finalize. Runs against the real
local MinIO (`make up`) — no mocking the thing under test, same principle as everywhere else in
this repo. Pure-function pieces (WAV wrapping, Opus transcoding) are tested independently of
MinIO, since they need neither a filesystem path nor object storage to be exercised."""

from __future__ import annotations

import io
import uuid
import wave
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import pytest

from services.realtime.app.audio.upload import (
    PEAKS_BUCKETS,
    checkpoint_upload,
    compute_peaks,
    encode_wav_to_opus_bytes,
    finalize_recording,
    get_s3_client,
    pcm_to_wav_bytes,
    read_pcm_prefix,
    recording_key_opus,
    recording_key_wav,
)
from services.realtime.app.core.config import get_settings


def _minio_reachable() -> bool:
    try:
        get_s3_client().list_buckets()
        return True
    except Exception:
        return False


def _tone_pcm(seconds: float, *, sample_rate: int = 16_000) -> bytes:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    return (np.sin(2 * np.pi * 220 * t) * 3000).astype(np.int16).tobytes()


def _s3_client() -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


class TestKeyConventions:
    def test_wav_and_opus_keys_share_the_delete_prefix_convention(self) -> None:
        user_id, session_id = uuid.uuid4(), uuid.uuid4()
        wav_key = recording_key_wav(user_id, session_id)
        opus_key = recording_key_opus(user_id, session_id)
        assert wav_key == f"users/{user_id}/sessions/{session_id}.wav"
        assert opus_key == f"users/{user_id}/sessions/{session_id}.opus"
        for key in (wav_key, opus_key):
            assert key.startswith(f"users/{user_id}/")  # matches user_service.delete_prefix


class TestPureTranscoding:
    """No S3, no filesystem — these exercise the actual byte-shuffling logic directly."""

    def test_pcm_to_wav_bytes_round_trips_through_the_wave_module(self) -> None:
        pcm = _tone_pcm(1.0)
        wav_bytes = pcm_to_wav_bytes(pcm)
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 16_000
            assert w.readframes(w.getnframes()) == pcm

    def test_read_pcm_prefix_skips_the_44_byte_header(self, tmp_path: Path) -> None:
        pcm = _tone_pcm(0.5)
        wav_path = tmp_path / "session.wav"
        wav_path.write_bytes(pcm_to_wav_bytes(pcm))
        assert read_pcm_prefix(wav_path) == pcm

    def test_read_pcm_prefix_on_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert read_pcm_prefix(tmp_path / "nope.wav") == b""

    def test_read_pcm_prefix_on_header_only_file_returns_empty(self, tmp_path: Path) -> None:
        wav_path = tmp_path / "empty.wav"
        wav_path.write_bytes(pcm_to_wav_bytes(b""))
        assert read_pcm_prefix(wav_path) == b""

    def test_opus_reencode_reduces_bytes_by_at_least_10x(self) -> None:
        """Task 2.2c acceptance criterion, verified directly: "Opus re-encode reduces stored
        bytes by >= 10x on a fixture." """
        pcm = _tone_pcm(10.0)
        wav_bytes = pcm_to_wav_bytes(pcm)
        opus_bytes = encode_wav_to_opus_bytes(wav_bytes)
        assert len(wav_bytes) / len(opus_bytes) >= 10.0

    def test_opus_reencode_preserves_duration(self) -> None:
        import av

        pcm = _tone_pcm(3.0)
        opus_bytes = encode_wav_to_opus_bytes(pcm_to_wav_bytes(pcm))
        with av.open(io.BytesIO(opus_bytes)) as container:
            stream = container.streams.audio[0]
            total_samples = sum(frame.samples for frame in container.decode(stream))
            duration_s = total_samples / stream.rate
        assert duration_s == pytest.approx(3.0, abs=0.05)


class TestComputePeaks:
    """Task 3.3a: the waveform summary — pure, no S3, no filesystem."""

    def test_returns_exactly_buckets_floats_in_range(self) -> None:
        peaks = compute_peaks(_tone_pcm(5.0))
        assert len(peaks) == PEAKS_BUCKETS
        assert all(0.0 <= p <= 1.0 for p in peaks)

    def test_silence_is_all_zero(self) -> None:
        silence = b"\x00\x00" * 16_000  # 1s of digital silence at 16kHz
        peaks = compute_peaks(silence)
        assert peaks == [0.0] * PEAKS_BUCKETS

    def test_full_scale_tone_has_peaks_near_one(self) -> None:
        t = np.linspace(0, 1.0, 16_000, endpoint=False)
        full_scale = (np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16).tobytes()
        peaks = compute_peaks(full_scale)
        assert max(peaks) > 0.95

    def test_empty_pcm_returns_all_zero_not_empty_list(self) -> None:
        assert compute_peaks(b"") == [0.0] * PEAKS_BUCKETS

    def test_shorter_than_buckets_recording_pads_remaining_buckets_with_zero(self) -> None:
        # 10 samples can't fill 1000 buckets one-for-one; the tail must be zero, not truncated.
        tiny = (np.full(10, 32767, dtype=np.int16)).tobytes()
        peaks = compute_peaks(tiny)
        assert len(peaks) == PEAKS_BUCKETS
        assert peaks[-1] == 0.0


pytestmark_minio = pytest.mark.skipif(not _minio_reachable(), reason="MinIO not reachable")


@pytestmark_minio
class TestCheckpointAndFinalize:
    @pytest.mark.asyncio
    async def test_checkpoint_upload_produces_a_playable_wav_object(self, tmp_path: Path) -> None:
        pcm = _tone_pcm(1.0)
        wav_path = tmp_path / "session.wav"
        wav_path.write_bytes(pcm_to_wav_bytes(pcm))

        user_id, session_id = uuid.uuid4(), uuid.uuid4()
        key = await checkpoint_upload(wav_path, user_id=user_id, session_id=session_id)
        assert key == recording_key_wav(user_id, session_id)

        settings = get_settings()
        client = _s3_client()
        obj = client.get_object(Bucket=settings.s3_bucket, Key=key)
        body = obj["Body"].read()
        assert obj["ContentType"] == "audio/wav"
        with wave.open(io.BytesIO(body), "rb") as w:  # raises if not a valid WAV
            assert w.getnframes() > 0

        client.delete_object(Bucket=settings.s3_bucket, Key=key)

    @pytest.mark.asyncio
    async def test_checkpoint_upload_on_empty_file_returns_none(self, tmp_path: Path) -> None:
        wav_path = tmp_path / "empty.wav"
        wav_path.write_bytes(pcm_to_wav_bytes(b""))
        result = await checkpoint_upload(wav_path, user_id=uuid.uuid4(), session_id=uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_checkpoint_upload_on_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = await checkpoint_upload(
            tmp_path / "does_not_exist.wav", user_id=uuid.uuid4(), session_id=uuid.uuid4()
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_finalize_uploads_opus_deletes_wav_checkpoint_and_local_file(
        self, tmp_path: Path
    ) -> None:
        """Task 2.2c: "After transcription, re-encode user audio to Opus... and delete the
        PCM." Exercises the full sequence: checkpoint (WAV) -> transcode -> upload (Opus) ->
        delete WAV object -> delete local file."""
        pcm = _tone_pcm(2.0)
        wav_path = tmp_path / "session.wav"
        wav_path.write_bytes(pcm_to_wav_bytes(pcm))
        original_wav_size = wav_path.stat().st_size

        user_id, session_id = uuid.uuid4(), uuid.uuid4()
        result = await finalize_recording(wav_path, user_id=user_id, session_id=session_id)
        opus_key = result.key
        assert opus_key == recording_key_opus(user_id, session_id)
        assert result.format == "opus"
        assert result.peaks is not None and len(result.peaks) == PEAKS_BUCKETS

        settings = get_settings()
        client = _s3_client()

        opus_obj = client.get_object(Bucket=settings.s3_bucket, Key=opus_key)
        opus_bytes = opus_obj["Body"].read()
        assert opus_obj["ContentType"] == "audio/ogg"
        assert original_wav_size / len(opus_bytes) >= 10.0  # CLAUDE.md §1.8's ~12x, verified

        # "Never store persona audio" is a different claim, but "the WAV checkpoint is not left
        # behind once Opus exists" is this test's job.
        wav_key = recording_key_wav(user_id, session_id)
        with pytest.raises(Exception):  # noqa: B017 — boto3 raises a botocore ClientError (404)
            client.get_object(Bucket=settings.s3_bucket, Key=wav_key)

        assert not wav_path.exists()  # local PCM deleted

        client.delete_object(Bucket=settings.s3_bucket, Key=opus_key)

    @pytest.mark.asyncio
    async def test_finalize_on_empty_recording_returns_wav_checkpoint_key_or_none(
        self, tmp_path: Path
    ) -> None:
        """Task 2.5's edge-case spirit applied here too: a session where no turn ever happened
        (silence throughout) must not crash finalize — there is nothing to transcode, so this
        degrades gracefully rather than raising."""
        wav_path = tmp_path / "empty.wav"
        wav_path.write_bytes(pcm_to_wav_bytes(b""))
        result = await finalize_recording(wav_path, user_id=uuid.uuid4(), session_id=uuid.uuid4())
        assert result.key is None
        assert result.format is None
        assert result.peaks is None


@pytest.mark.asyncio
async def test_finalize_recording_returns_none_fields_when_storage_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`get_settings()` is `@lru_cache`d to one singleton per process — mutating that instance's
    attribute (what `monkeypatch.setattr` does here) is visible to `upload.py`'s own
    `get_settings()` calls without needing to touch the cache/function itself, and monkeypatch
    restores the attribute automatically at teardown."""
    wav_path = tmp_path / "session.wav"
    wav_path.write_bytes(pcm_to_wav_bytes(_tone_pcm(0.2)))

    monkeypatch.setattr(get_settings(), "s3_bucket", "")
    result = await finalize_recording(wav_path, user_id=uuid.uuid4(), session_id=uuid.uuid4())
    assert result.key is None
    assert result.format is None
    assert result.peaks is None
    assert wav_path.exists()  # never touched — nothing was ever uploaded to delete it after
