# 0009 — Task 2.2c: periodic checkpoint re-upload instead of true S3 multipart

Task 2.2c asks for "Multipart upload, one part per ~30s of audio... Finalize the multipart
upload in the sweeper," superseding `docs/decisions/0007-recording-upload-not-incremental.md`'s
Phase 1 simplification (upload once, at finalize). This implements the *intent* — audio durable
in object storage during the session, not only at the end — with a different mechanism, for two
concrete reasons.

## Why not literal S3 multipart

1. **The part-size math doesn't work.** 16kHz mono PCM16 is 32,000 bytes/second — 30 seconds is
   960,000 bytes. S3 (and MinIO, which mirrors S3's API) rejects any multipart part under 5 MiB
   except the *last* one (`EntityTooSmall`). "One part per ~30s" would fail on the second
   `UploadPart` call every time. Getting a compliant part size means buffering ~2.5+ minutes of
   audio before each upload — a materially different design from what "one part per 30s" reads
   as.
2. **An incomplete multipart upload is a real footgun, and this task is explicitly about crash
   safety.** If the process dies before `CompleteMultipartUpload`, the uploaded parts are not a
   readable, playable object — they're billed, orphaned storage that needs a lifecycle rule to
   ever clean up, and "killing the process mid-session leaves a playable partial recording in
   object storage" (Task 2.2's own acceptance criterion) is **not true** of an incomplete
   multipart upload. The mechanism this task asks for doesn't actually satisfy the property it's
   graded on.

## What this implements instead

A periodic **checkpoint re-upload**: every `RECORDING_CHECKPOINT_INTERVAL_S` (60s) of session
time, and once more at finalize, the bytes written to the local WAV so far are read (via a fresh
read-only handle — the write handle Task 1.2c already keeps open is never touched), wrapped in a
fresh, correctly-headered WAV, and `PutObject`'d to the same final key
(`users/{user_id}/sessions/{session_id}.wav`), overwriting the previous checkpoint. The object at
that key is therefore **always either "the recording so far" or "the complete recording" — a
complete, playable object at every point**, never a dangling fragment. This is simpler than true
multipart, has no cleanup-on-crash story to get wrong, and satisfies every acceptance criterion
in Task 2.2's list ("uploads as the session runs," "a crash leaves a playable partial
recording") more directly than multipart would.

The tradeoff, named honestly: this re-uploads the whole file on each checkpoint rather than only
the new bytes, so bandwidth is O(n²) in session length rather than O(n). At this project's scale
(sessions capped at 30 minutes, `target_minutes ∈ {5,10,20,30}`, giving a worst case of ~58 MB of
16-bit PCM re-uploaded on the final few checkpoints) this is a deliberate, bounded cost, not a
production-scale concern.

## Opus re-encoding

Task 2.2c also asks for user audio to be re-encoded to Opus at 24kbps after transcription, with
the PCM deleted (~12x reduction). `services/realtime`'s dependency list already includes `av`
(PyAV, a libav/ffmpeg binding) for a different purpose (none, actually — it was declared in
Phase 1 but unused); it has a working `libopus` encoder, so this needed no new dependency. The
re-encode happens once, at finalize, after the last checkpoint: the WAV is transcoded to an Ogg
Opus container and uploaded to `users/{user_id}/sessions/{session_id}.opus`; the WAV object and
local PCM file are then deleted. The checkpoint WAV object is deliberately allowed to exist
*during* the session (there is nothing to transcode losslessly from yet, and the whole point of
the checkpoint is a durable *original*-fidelity snapshot while the session is still live) —
Opus is a post-session storage optimization, not a live-session one.
