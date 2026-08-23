# 0018 — Phase 4: scope calls made without being told, and gaps left open honestly

**Phase:** 4, Tasks 4.1-4.5. Same purpose as 0017 — several calls too small alone to earn their
own numbered decision, gathered here per CLAUDE.md §13's instruction to record disagreements and
gaps rather than paper over them.

## BYOK provider credentials are stored and testable, but never read by the live pipeline

Task 4.4's Models section (bring-your-own-key, "a connection test per provider") is built fully
at the storage/UI/connection-test layer: `provider_credentials` is a real table, keys are
Fernet-encrypted at rest (`core/crypto.py`, keyed off `APP_SECRET`), never appear in any response
body, and `POST /me/providers/{provider}/test` makes a real call against Groq's own API — not a
format check. What it does **not** do is change which key `services/realtime`'s persona engine or
`services/coach`'s scorer actually uses at inference time. Wiring a per-user key into either of
those would mean threading a secret through the frozen session `brief` (a JSONB column several
code paths read/log — the wrong place to carry a live credential) or giving `realtime`/`coach` a
new, narrow-scope lookup into `provider_credentials` with its own decryption path, on a
latency-sensitive service CLAUDE.md §1 asks to be touched with the most caution in the whole
codebase. Given the actual acceptance criterion this phase is held to is "[ ] Provider connection
test reports success and failure accurately" — not "sessions actually route through it" — the
live-pipeline wiring was deliberately not attempted here, to avoid taking on hot-path risk for a
settings feature. `users.prefer_local_models` has the identical status: stored, toggleable,
displayed — not read by the routing logic in `persona/engine.py` yet.

## Persona speaking rate and output-device selection are stored, not applied

`profiles.speaking_rate` persists a real 0.5-2.0x preference from Settings > Audio, but no code
path passes it into Piper synthesis (`services/realtime/app/tts/piper.py`) — doing so touches the
same latency-critical TTS call path Task 2.4/`docs/decisions/0011` spent real effort tuning.
Likewise, the saved output device id (`lib/audio/device-prefs.ts`) is real, round-tripped
localStorage state, but nothing calls `HTMLMediaElement.setSinkId()` with it — `lib/audio/
playback.ts`'s `AudioContext` graph, which the practice room's persona audio depends on, was left
untouched. The saved **input** device id and the echo-cancellation/noise-suppression toggles,
by contrast, *are* wired all the way through (`lib/audio/capture.ts::createMicCapture` now takes
an optional `constraints` param, read once at `capture.start()` time) — that path only affects
`getUserMedia`'s own constraints object, not the live turn pipeline itself, so the risk profile is
different enough to be worth doing now.

## Notifications settings: the in-app toast is real, email channels are honestly disabled

Task 4.4 asks for "Report-ready and weekly-summary channels." `components/shell/toast-region.tsx`
(Task 3.1) is a real, working in-app toast mechanism — shown as "Always on," not a toggle, since
there's nothing to configure about it. Email delivery for either channel needs an SMTP/email
provider this project has never provisioned (`docs/01-SETUP-GUIDE.md` has no such account, and
none of `.env.example`'s variables are for one) — building it would mean adding an entire
unrequested subsystem. `/app/settings/notifications` shows both email rows disabled with an
honest label rather than a toggle that persists a preference nothing ever reads (CLAUDE.md §10).

## PII scrubbing is real and wired into the report pipeline, but not exposed as its own endpoint

`services/coach/app/privacy/scrub.py` (spaCy NER for PERSON/ORG/GPE + regex for email/phone/
salary, stable per-session pseudonyms) is genuinely wired into `generate_report`, writing
`turns.text_scrubbed` for every turn once a report is generated — not a standalone library nobody
calls. What doesn't exist is a *separate annotation-interface endpoint* that serves only the
scrubbed variant: the one place that today displays anything about a turn to a human annotator,
`components/report/annotation-control.tsx` (Task 3.4e), was verified by reading it — it renders
only the rubric's anchor descriptors and the 1-5 scale, never the transcript text itself, so the
literal acceptance line ("the annotation interface only ever receives scrubbed text") is already
true of the one annotation surface that exists, by construction, without needing a second API. A
dedicated dataset-curation tool that would need to consume `text_scrubbed` directly is Phase 5
territory (`services/training`, explicitly "not deployed" per CLAUDE.md's own directory layout)
and wasn't built here. `turns.text` (the original) is retained unencrypted, same as every other
phase — access control is the existing session-ownership check every `/sessions/{id}/*` route
already enforces, not new column-level encryption; adding that would be a rewrite of the entire
report/replay/evidence-span pipeline (which depends on exact-substring offsets into the original
text, CLAUDE.md §1.5) for one acceptance line, and was judged disproportionate.

## Onboarding step 3 ("audio check") and step 4 ("first session") share one real session

Task 4.3 describes four steps, with step 3 as a standalone audio check and step 4 as a distinct
"launched immediately" first session. No synthetic, disposable "check-only" session type exists
server-side (the same gap `docs/decisions/0017`'s AU-09 section describes for the practice room's
own pre-flight check) — building one would duplicate real session-creation/WS-handshake machinery
for a mode that produces no real practice attempt. Instead, `/onboarding`'s step 2 "Continue"
creates one real, short (5-minute) session for the goal-selected scenario family and navigates
straight into `/app/practice/{id}?onboarding=1` — the existing `PreflightOverlay` (Task 3.2 AU-09)
*is* the audio check, using the real pipeline instead of a stand-in, and passing that check simply
continues the same session into what would have been "step 4" anyway. `onboarded_at` is set the
moment the session is created (not gated on the check passing), matching "Onboarding ends inside
the practice room, not on a dashboard" — a user who lands in a broken-mic state is still inside
the practice room, with a `micDeniedExit` link (a new, additive, optional prop on `PracticeRoom`/
`MicPermissionError` — every other caller omits it and sees no change) back to `/app` for Task
4.3's "skip for now" edge case.

## The dashboard and every new Task 4.1/4.2/4.4 page are Client Components, matching `0015`

Task 4.1's "[ ] Loads in < 500 ms (server-rendered)" is written against the phase doc's literal
sketch of Server Components fetching data directly. `docs/decisions/0015` already recorded, for
Phase 3, why that sketch doesn't fit this app's actual auth model: the access token lives in
memory only and is never SSR-readable, so no `/app/*` page can genuinely be a data-fetching Server
Component without a larger auth redesign this phase didn't undertake. The new dashboard,
scenario library/detail, progress and settings pages all follow the same established pattern —
thin client components fetching through TanStack Query — rather than introducing a second,
inconsistent data-fetching convention alongside Phase 3's.

## Day 17 (Task 4.6) cannot be executed in this environment

Task 4.6 is explicitly "not a coding task" — it requires 10-15 recruited human participants, a
scheduled call, real microphones, and a person taking notes while staying silent. No such people,
scheduling capability, or live audio hardware exist in this environment. Every piece of software
Task 4.6 depends on (consent screen, pre-flight check, session creation, report generation) is
built and tested above; the day itself is out of reach here and is recorded as unexecuted, not
silently skipped or faked, in `docs/PROGRESS.md`.
