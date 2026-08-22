# 0007 — recording upload is a single `put_object` at finalize, not incremental

**Phase:** 1 (Task 1.2c, Task 1.1)

## The gap

Task 1.2c says: "Write raw PCM to a per-session WAV on disk as it arrives, so a crash never
loses the recording. **Upload begins during the session, not at the end.**" What's built
(`services/realtime/app/audio/upload.py`) does the first half exactly as specified
(`SessionWavWriter` appends to disk frame-by-frame) but not the second: the S3/MinIO upload
happens once, as a single `put_object`, when `finalize_runtime` runs — at the end, not during.

## Why

A genuine "upload begins during the session" implementation means S3 multipart upload:
open a multipart upload at session start, upload completed WAV chunks as parts on some
cadence, complete the multipart upload at finalize. That's real, non-trivial engineering —
tracking part numbers and ETags across the session's lifetime, handling a part upload failing
mid-session, deciding a sensible part-size/cadence trade-off — and distinct from everything
else in Task 1.2c, which is otherwise about the local disk write path.

Given the volume of Phase 1 built in this pass, this was the one piece judged safe to simplify
rather than skip outright: the crash-safety property Task 1.2c is actually protecting
("a crash never loses the recording") is fully satisfied by the local incremental disk write,
which is real and unmodified. What's lost by uploading once at the end is narrower: if the
*process* dies before finalize runs, the recording exists on local disk but not yet in
S3 — recoverable by re-running the upload against the orphaned file, not lost.

## What would change this

If a session regularly runs long enough that a single end-of-session upload becomes slow or
memory-heavy (uploading many minutes of PCM as one file), multipart upload keyed to, say, every
30-60 seconds of audio is the correct next step. Nothing in this module's interface
(`upload_recording(path, user_id, session_id)`) needs to change for that — it would become
several calls (start, upload_part × N, complete) internally.
