# Phase 3 — BUILD — The practice room and the report (days 13–15)

Build specification for Claude Code. Read `CLAUDE.md`, `docs/10-frontend-shell.md`,
`docs/11-practice-room.md` and `docs/12-report-surface.md` first.

**Prerequisite: the Day 8 gate passed and Phase 2's latency budget is met.** If a spoken
conversation does not work from the CLI, stop and go back. Building this UI on a broken
pipeline wastes three days.

**Exit criterion:** a live browser session works end to end, and the report renders with
synchronised replay.

---

## TASK 3.1 — Design system and app shell

### Tokens (`apps/web/app/globals.css` + Tailwind config)

```
Surfaces        page / card / raised. Separation via 1px border + subtle bg shift.
                NO shadows.
Typography      one sans (2 weights: 400, 500), one mono for identifiers and metrics.
                EXACTLY six sizes: 12, 13, 15, 17, 22, 32. Do not add a seventh.
Score colours   --score-strong (green) --score-developing (amber) --score-weak (red)
                --score-insufficient (slate)
                RESERVED. These four variables may not be used for anything except
                rubric values, anywhere in the application.
Accent          exactly one accent colour, used for primary actions only
Spacing         4px base scale; every gap/pad/margin is a multiple
Motion          <200ms state changes, 400ms panel transitions.
                The speaking indicator and the replay playhead are the ONLY
                continuous animations. All motion honours prefers-reduced-motion.
Icons           one outline set (lucide), 16px inline / 20px standalone
```

Dark-first with a **genuinely designed** light mode — not an inversion.

### Persistent chrome (every authenticated page **except** the practice room)

- Collapsible left sidebar with primary nav and a practice-minutes-this-week meter pinned
  at the bottom.
- Top bar: breadcrumb, a prominent **Start practice** action, user menu. The primary action is
  always one click away because the product's value is entirely in sessions completed.
- Command palette (⌘K): fuzzy search across scenarios, sessions and settings, plus verbs —
  *start session*, *repeat last scenario*, *toggle theme*.
- Toast region, bottom right, used almost exclusively for *"your report is ready"*.

### Cross-cutting requirements

| Concern | Requirement |
|---|---|
| Loading | Skeletons matching **final layout dimensions**. No layout shift when content arrives. |
| Empty states | Every list has a designed empty state: one sentence, one primary action. |
| Error states | Distinguish mic-denied / network / model-unavailable / not-found. Each offers a recovery path, never a stack trace. |
| Mic permission | Requested **only at the moment it is needed**, with the reason stated first. Never on page load. |
| Accessibility | Full keyboard operation, ARIA live regions for turn state, visible focus rings. |
| Reduced motion | Amplitude ring degrades to a static state indicator. |
| Responsive | Full functionality to tablet width. Practice room works on mobile web. Report collapses to a stacked layout rather than hiding the replay. |
| Deep linking | Report view state (selected turn, playhead position, active criterion) encoded in the URL and restorable. |

### Acceptance criteria

- [ ] Tokens defined once; a lint rule or CI grep fails if a raw hex colour appears in a component
- [ ] Score colours appear **only** in rubric-value contexts (grep-verified)
- [ ] Exactly six font sizes are defined and used
- [ ] Dark and light both render every surface correctly
- [ ] `prefers-reduced-motion` disables all continuous animation
- [ ] Command palette opens on ⌘K and its verbs work
- [ ] Every list has an empty state

---

## TASK 3.2 — The practice room ⭐ THE PAGE THE PROJECT IS JUDGED ON

`app/app/practice/[sessionId]/page.tsx`

Budget the full day. Build it only after the pipeline it drives is proven from the CLI.

### Structure

```
page.tsx                    Server Component — fetches session, scenario, persona
 └─ <PracticeRoom/>         "use client" — THE ONLY CLIENT BOUNDARY on this route
     ├─ usePracticeStore    Zustand: clientState, micLevel, caption, elapsed, connection
     ├─ useAudioCapture     worklet + getUserMedia (from Task 1.2a)
     ├─ useRealtimeSocket   WS lifecycle, resume, message dispatch
     └─ usePlaybackQueue    scheduled playback (from Task 1.5c)
```

**No persistent chrome on this route.** No sidebar, no breadcrumb, no top bar.

### Layout — the screen is almost empty

Centred vertically, in this order and nothing else:

1. **Persona presence.** One large circular element with the persona's name and an
   amplitude-reactive ring:
   - `listening` → gentle pulse
   - `speaking` → **driven by real playback amplitude**, sampled from an `AnalyserNode`
   - `thinking` → a distinct, restrained state (not a spinner, not the listening pulse)
2. **Caption line.** One or two lines. Live partial transcript while the user speaks; persona
   line while it speaks. Toggleable, **remembered per user**.
3. **"Your turn" indicator.** Unmistakable, non-verbal.
4. **Session timer.** Elapsed and remaining, unobtrusive.
5. **Controls.** Mute, end session, captions toggle. Nothing else.

### The four client states

Map from `state_change.client_state` only — **do not re-derive machine states in the frontend.**

`your_turn` · `thinking` · `speaking` · `connection_trouble`

### Non-negotiable behaviours — these are acceptance criteria, not suggestions

1. **Microphone level meter visible at all times.** Driven by the worklet's RMS messages at
   ≥ 20 Hz. **Must not go through React state** — write to a ref/CSS custom property. Silence
   must never be ambiguous.
2. **The thinking state appears within 200 ms of endpointing, before the reply is ready.**
   Triggered by the `state_change` message, not by the arrival of audio.
3. **Ending never loses the recording.** Upload runs during the session; end triggers a flush,
   not an upload.
4. **Connection loss shows a calm reconnection state and resumes** — never dumps the user to a
   dashboard.
5. **`Escape` does not end the session.** Ending requires a confirmed action.
6. **Closing the tab** triggers `beforeunload` confirmation and a synchronous flush of buffered
   audio.
7. **Real amplitude only.** No looping fake waveform anywhere. Users notice.

### Pre-flight audio check (AU-09)

Before the first session ever: a three-second "say hello" test verifying capture → transport →
ASR → playback end to end, with the transcript shown back. A first session that silently fails
is an unrecoverable first impression.

### Edge cases

| Case | Required behaviour |
|---|---|
| Mic permission denied | **Browser-specific recovery instructions** (Chrome / Firefox / Safari differ, and macOS adds an OS layer). Not a generic message. |
| Mic permission revoked mid-session | Detect via track `ended` event; pause, show recovery, allow resume |
| No input device | Device picker with a clear message; do not start the session |
| Device changes mid-session (headphones unplugged) | Detect `devicechange`, re-acquire, notify calmly |
| Tab backgrounded | `AudioContext` may suspend — detect and resume; warn if the OS throttles |
| Network drops for 5 s | `connection_trouble`, auto-reconnect with resume, no data loss |
| Network drops for 2 min | Session finalised; user sees "session saved" not an error |
| Session already ended | Redirect to the report |
| Not the session owner | 404 |
| Two tabs, same session | Second tab shows "this session is open elsewhere" and does not connect |

### Acceptance criteria

- [ ] A full 10-minute session runs in the browser with no glitches
- [ ] Level meter visibly responds to voice and reads zero when muted
- [ ] Thinking state measurably appears within 200 ms of endpointing (test with timestamps)
- [ ] Amplitude ring is driven by an `AnalyserNode`, verified by muting the output
- [ ] Killing Wi-Fi for 5 s reconnects and resumes with no lost audio
- [ ] `Escape` does nothing; the end button requires confirmation
- [ ] Tab close prompts and flushes
- [ ] Mic-denied shows browser-specific instructions in Chrome and Firefox
- [ ] Screen reader announces every turn state change via an ARIA live region
- [ ] Reduced-motion mode replaces the ring with a static indicator
- [ ] Zero client components outside the single island (verified by inspection)

---

## TASK 3.3 — Report I: transcript, scores, delivery, waveform

`app/app/sessions/[id]/page.tsx` — Server Component shell with client islands for the player.

### 3.3a — Server-side peak precomputation

**Required before the UI.** When a recording is finalised, compute a peaks array
(~1000 buckets) and store it with the session.

Decoding a 20-minute WAV in the browser to draw a waveform is a two-second freeze on first
render. Never do it client-side.

### 3.3b — Header

Scenario, persona, difficulty, duration, date, **overall score with delta against the user's
previous attempt**, and actions: Practise again · Retry one question · Share · Export ·
Delete recording.

### 3.3c — Verdict block

Three sentences of summary, then three strengths and three improvements, **each linking into
the moment that justifies it**. No generic encouragement — the narrator's blocklist from Task
2.5g enforces this server-side; the UI must not add its own.

### 3.3d — Score panel

One row per criterion:
- score, confidence indicator, a **miniature bar against the user's own history**
- **the rubric anchor text for that value** — the same words the annotator saw
- an expander revealing contributing turns

Criteria below the confidence threshold render **"not enough signal"** — never a number, never
a greyed-out number, never a dash that could be read as zero.

### 3.3e — Delivery panel

Words per minute, filler rate, mean and longest answer, talk-time share, plotted across the
session. These are deterministic values from `turn_metrics` and should be visually
distinguished from model judgements — different treatment, not the same score chip. **The user
must be able to tell arithmetic from judgement at a glance.**

### 3.3f — Waveform

wavesurfer.js with:
- precomputed peaks (never client-side decode)
- turn boundary regions
- score markers on the timeline
- a draggable playhead

Destroy the instance on unmount — otherwise an `AudioContext` leaks per report opened.

### 3.3g — Progressive rendering

```
immediately        transcript, delivery metrics, waveform, metadata
as scores arrive   score panel rows fill in individually
when ready         verdict block appears
```

Subscribe to the Redis `report-ready` channel via SSE or polling. Skeletons match final layout
dimensions exactly.

### Acceptance criteria

- [ ] Report opens in < 1 s for a 20-minute session (peaks precomputed)
- [ ] Score panel shows "not enough signal" where confidence is below threshold
- [ ] Anchor text for the achieved score value is displayed on every criterion row
- [ ] Delivery metrics are visually distinct from model-judged scores
- [ ] A report whose coach job has not finished renders transcript + delivery immediately
- [ ] Score rows fill in progressively without layout shift
- [ ] wavesurfer is destroyed on unmount (no AudioContext leak across 10 opens)

---

## TASK 3.4 — Report II: synchronised replay

**The hero surface.** Everything must move together.

### 3.4a — One source of truth

`playheadMs` in a Zustand store. Everything derives from it:

```ts
const currentTurn = useMemo(
  () => turns.find(t => playheadMs >= t.start_ms && playheadMs < t.end_ms),
  [playheadMs, turns]
);
```

- wavesurfer's `audioprocess` fires at ~60 Hz. **Throttle store writes to ~10 Hz.** Read
  `currentTime` directly for the playhead visual so it stays smooth.
- Do not let any component hold its own notion of "where we are". That produces drift you will
  never fully fix.

### 3.4b — What must stay in sync

| Component | Behaviour |
|---|---|
| Waveform | Playhead position; turn regions; score markers |
| Transcript | Auto-scrolls, current turn highlighted |
| Score panel | Shows the current turn's criterion scores |
| Turn detail | Transcript, delivery metrics, criterion scores, coach rationale |

### 3.4c — Interactions

- **Click any evidence span** → seek audio to that moment (RP-02). This is the single most
  persuasive interaction in the demo.
- Click a transcript word → seek there.
- Click a score marker → seek and open that turn.
- Controls: play, pause, previous/next turn, **jump to lowlight**, speed up to 1.5×.

### 3.4d — Transcript

Speaker-labelled, timestamped, **evidence spans underlined**, click any word to seek. Each user
turn carries inline scores and, where available, the coach's rewrite shown against the original.

**Persona audio is regenerated on demand** during replay from the transcript + `voice_id` — it
was never stored. Cache regenerated audio client-side for the session so scrubbing back does
not re-synthesise.

### 3.4e — Annotation control (CS-15)

A discreet per-turn control to record a human score against any criterion. Opens a compact
panel showing the **full anchor descriptors** and the five-point scale. Writes an `annotations`
row with `round = 1`.

**This is how the training set grows without a separate tool.** Do not cut it — it is
disproportionately valuable relative to its size.

**The annotator must never see the model's prediction while labelling.** Hide the model score
in the annotation panel; that contamination would invalidate every agreement figure you compute
later.

### 3.4f — Retry one question (RP-08)

Re-run a single question in isolation: creates a new short session seeded with that one
question, in the same scenario, at the same difficulty, and links the result back to the
original turn for comparison.

### 3.4g — Deep linking

Report view state — selected turn, playhead position, active criterion — encoded in the URL and
restorable. `?turn=7&t=142300&criterion=structure`.

### Edge cases

| Case | Required behaviour |
|---|---|
| Recording deleted (retention expired) | Transcript and scores still render; replay controls disabled with a clear explanation |
| Persona audio regeneration fails | Transcript still readable; seek still works on user turns |
| Turn has no scores | Panel shows "not enough signal", not empty space |
| Session with 1 turn | Replay still works; delivery chart handles a single point |
| Evidence span offsets out of range (data bug) | Span not rendered; logged; score still shown |
| Very long session (30 min, 60 turns) | Transcript virtualised; scrolling stays at 60 fps |

### Acceptance criteria

- [ ] Dragging the playhead moves transcript, turn highlight and score panel simultaneously
- [ ] Clicking an evidence span seeks to that exact moment (verified against word timings)
- [ ] Jump-to-lowlight works
- [ ] Annotation control writes an `annotations` row and **never displays the model's prediction**
- [ ] Retry-one-question creates a linked short session
- [ ] URL state restores exactly on reload
- [ ] 60-turn transcript scrolls at 60 fps (virtualised)
- [ ] Report with an expired recording degrades gracefully

---

## Phase 3 definition of done

- [ ] Design tokens defined; score colours reserved and grep-verified
- [ ] App shell with sidebar, top bar, command palette, toasts
- [ ] Practice room runs a full live session with all seven non-negotiables verified
- [ ] Pre-flight audio check working
- [ ] Report renders progressively, opens in < 1 s
- [ ] Synchronised replay with click-to-play evidence
- [ ] Annotation control present and prediction-blind
- [ ] Retry-one-question working
- [ ] Accessibility: keyboard, ARIA live regions, reduced motion all verified
- [ ] No client components outside the practice-room island
