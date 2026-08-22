# 0017 — Report UI: presentation choices made without being told, and gaps left open honestly

**Phase:** 3, Tasks 3.3/3.4. One doc for several small calls, each too small alone to earn its
own numbered decision, gathered here per CLAUDE.md §13's instruction to record disagreements
and gaps rather than paper over them.

## Score bands are a UI-only convention, not a backend contract

`components/score/score-color.ts` bands a 1-5 `aggregate_score`/`score` into
strong (>= 4) / developing (>= 2.5) / weak (< 2.5) to pick a reserved colour. No document
specifies exact thresholds for the three reserved colours against the rubric's 1-5 scale; these
are a reasonable, symmetric split I chose, isolated to one file specifically so it can be
retuned without touching any component that renders a score.

## Waveform score markers mark the report's highlight/lowlight turns, not a per-turn average

Task 3.3f asks for "score markers on the timeline." The only genuinely *authoritative*
per-turn-position signal the coach already computes is `Report.highlight_turn_id` /
`.lowlight_turn_id` (`services/coach/app/report/aggregation.py::pick_highlight_and_lowlight`) —
so those two get markers, in the two reserved colours, and "jump to lowlight" (Task 3.4c) uses
the same data. An alternative — averaging each turn's own criterion scores into a per-turn
number for a marker at every turn — was rejected: it would be a new, un-reviewed aggregate
invented client-side and presented as if it meant something, which is exactly what CLAUDE.md
§10 ("never fabricate a metric") warns against, even though no single number would technically
be *wrong*.

## "The coach's rewrite shown against the original" (Task 3.4d) — not built

No schema anywhere in `services/coach` produces a rewritten version of a user's answer —
`TurnScore.rationale` is the scorer's own explanation of *why* it gave a score, explicitly never
shown to the user as-is (CLAUDE.md §1.4), and `NarrativeResult` has no comparable field. Building
this would mean generating new user-facing prose from a model with no spec for what it should
say or how it should be checked against the same blocklist/contradiction rules the rest of the
narrator's output goes through — genuinely new scope, not implemented.

## "Share", "Export", "Delete recording" (Task 3.3b) — shown, disabled, not wired

`components/report/report-header.tsx` renders all three buttons in the spec's own information
architecture, each disabled with a `title="Coming soon"` tooltip, rather than either silently
dropping them from the layout or building fake handlers. No backend endpoint exists for any of
the three (a public share link, a data/PDF export, or deleting one session's recording
independent of full-account deletion) — `DELETE /me` (AS-05) is the only existing deletion path,
and it removes everything for the account, not one recording.

## Transcript "virtualization" is `content-visibility: auto`, not a windowing library

Task 3.4's acceptance criterion is "60-turn transcript scrolls at 60 fps (virtualised)." Rather
than add a list-virtualization dependency, every transcript row gets
`content-visibility: auto` + `contain-intrinsic-size` (`components/report/transcript.tsx`),
which lets the browser skip layout/paint for off-screen rows without windowing the DOM. This is
a real, load-bearing performance technique, not a stand-in — but it has not been measured
against an actual 60-turn session in a real browser (no browser available in this environment;
see docs/PROGRESS.md's "verified vs. assumed" section for Phase 3).

## The pre-flight check (AU-09) reuses the real pipeline instead of a synthetic mode

Task 3.2 describes "a three-second 'say hello' test verifying capture -> transport -> ASR ->
playback end to end." No backend concept of a disposable pre-flight session exists (a WS token
is minted for, and scoped to, one real session — there's no throwaway variant). Building one
would mean new realtime-service surface with no clear owner (a session that exists but never
counts as a real practice attempt). Instead, `components/practice/preflight-overlay.tsx` makes
the *first real exchange* of an actual session legible as the check: the scripted opening line
(Task 2.3f, already spoken automatically) is the speaker proof, the user's first reply streaming
back as a live partial transcript is the capture/transport/ASR proof, and the overlay just
narrates that this is happening rather than gating on a separate mode. It uses the same pipeline
the rest of the session does, so it can't pass while the real thing is broken — the specific
failure mode AU-09 exists to catch.
