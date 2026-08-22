# 0014 — Persona-audio-on-replay lives in `services/realtime`, behind a new non-burning token

**Phase:** 3, Task 3.4d ("Persona audio is regenerated on demand during replay from the
transcript + voice_id — it was never stored").

## Why `POST /synthesize` is a new route on realtime, not on api

CLAUDE.md's own repo layout is explicit: `services/api/` is "Stateless. **Never touches
audio.**" `services/realtime/` already owns Piper (`tts/piper.py`), already has every voice
warmed in memory at process startup (`VoicePool`), and is the only service with a reason to ever
call `synthesize_chunk`. Putting this endpoint on api would mean either duplicating the TTS
stack into a second process or having api call into realtime's internals across the workspace
boundary that decision 0003 established specifically to keep these services independent.
Realtime already has everything this needs; api has none of it.

This is a plain REST route on realtime's existing FastAPI app, not a WebSocket message — the
practice-room WS protocol (`docs/03-realtime-protocol.md`) is frozen and this isn't a live-turn
concern at all. A report can be replayed long after the session's `SessionRuntime` was torn
down, so it needs to work with no live session in memory — `POST /synthesize` takes a voice_id
and text and returns audio, full stop, with no session state involved beyond the auth check
below.

## Why a new token type instead of reusing the WS token

`mint_ws_token`/`validate_and_burn_ws_token` are single-use by design (docs/phase-0-LEARN.md
§7) — burning the `jti` on first use is exactly right for a handshake that happens once per
connection, and exactly wrong for a replay session where the user scrubs back and forth and
each `/synthesize` call for regenerated audio is a *separate* request. Reusing the WS token
mechanism would mean the second play-this-line click of a report session always fails.

So: `mint_replay_token` (api) / `validate_replay_token` (realtime) — same secret
(`WS_TOKEN_SECRET`), same HS256 scheme, same "realtime never verifies an access/refresh token
itself" boundary the WS token already established, but **no Redis burn**, a longer TTL (1 hour,
vs. the WS token's 120 seconds), and a `typ: "replay"` claim so a replay token can never be
mistaken for (or substituted as) a real WS handshake token. `POST /sessions/{id}/replay-token`
mints one only after `CurrentUser`/`_get_owned_or_raise` has already proven the caller owns
that session — the token itself is what proves that to realtime afterwards, so realtime never
needs its own database round trip to `sessions`.

## What happens on failure

No deadline/fallback-voice/holding-line chain (Task 1.5b's cascade is a turn-path concern; this
isn't on any latency budget). A slow or failed synthesis call surfaces as one unplayable line in
the transcript — Task 3.4's own edge case table: "Persona audio regeneration fails -> transcript
still readable, seek still works on user turns." `apps/web/lib/report/persona-audio-cache.ts`
returns `null` rather than throwing on any failure, by design.
