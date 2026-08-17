# Phase 3 — LEARN — The practice room and the report (days 13–15)

**Exit criterion:** a live session runs in the browser, and the report renders with a
synchronised replay where the waveform, transcript, highlighted turn and score panel all move
together.

**Study time this phase:** ~6 hours — wavesurfer.js 3h, design-system decisions 2h, Zustand 1h.
**Heavy technologies:** none. The hard engineering is behind you; this phase is about restraint.

---

## 1. Two surfaces, two completely different jobs

Everything else in this application is a table or a form you can build in an afternoon. These
two are not.

| | The practice room | The report |
|---|---|---|
| Job | Get out of the way while someone speaks | Convert a session into something actionable in under two minutes |
| Design | Nearly empty | Dense data application |
| Decides | Whether the demo lands | Whether users come back |
| Hardest part | State clarity under latency | Synchronisation across four components |

The practice room is **simultaneously the hardest engineering and the most restrained design in
the whole specification.** That combination is unusual and it is why it gets its own day.

---

## 2. The practice room: why almost nothing is on screen

Anything on that screen is a distraction from talking. The user is nervous, speaking out loud,
possibly for the first time in weeks. Every element you add competes with the thing they came
to do.

What is on screen:

- **The persona presence.** One large circular element with the persona's name and an
  amplitude-reactive ring. It pulses gently while listening, animates with **real audio
  amplitude** while speaking, and shows a distinct restrained state while thinking.
- **The caption line.** One or two lines beneath, showing the live partial transcript while the
  user speaks and the persona line while it speaks. Optional, remembered per user — some people
  find captions grounding, others find them distracting.
- **The "your turn" indicator.** Unmistakable, non-verbal. This single element resolves the most
  common confusion in voice interfaces: *whose turn is it?*
- **A session timer.** Elapsed and remaining, unobtrusive.
- **Controls.** Mute, end, captions toggle. Nothing else.

That is the whole page. There is no sidebar, no breadcrumb, no navigation chrome. Every other
authenticated page has persistent chrome; this one deliberately does not.

### The four states, not eight

Your state machine has eight states. The user perceives four:

```
your turn  ·  thinking  ·  speaking  ·  connection trouble
```

Exposing more is noise. Exposing fewer makes the interface feel broken during any pause — if
"thinking" looks identical to "your turn", the user starts talking over the persona and the
whole rhythm collapses.

### The three non-negotiables

**1. A visible microphone level meter at all times.**
Silence must never be ambiguous. The worst possible first-run failure is a session that is
silently not recording, which the user only discovers at the end. A meter that visibly responds
to their voice removes that class of failure entirely. Drive it from the worklet's RMS
messages, not from the main thread.

**2. The thinking state appears within 200 ms of endpointing — before the reply is ready.**
This is the most important perceptual fact in the project: **perceived latency is dominated by
the delay before *any* feedback, not by total delay.**

A 1.4-second reply where something acknowledges you at 200 ms feels responsive. A 1.0-second
reply with nothing happening for a full second feels broken. You can win perceived latency you
did not win in engineering, for free, by acknowledging early.

Use a thinking indicator, **never a spinner**. A spinner says "the software is loading". A
subtle pulse says "the person is considering". They mean different things.

**3. Ending never loses the recording.**
Upload begins during the session (Phase 2, Task 2.2c). By the time the user clicks end, most of
the audio is already durable.

Plus: connection loss shows a calm reconnection state and resumes rather than dumping the user
to a dashboard. `Escape` does not end the session — ending requires a confirmed action. Closing
the tab triggers a confirmation and a synchronous flush of buffered audio.

### Real amplitude, never fake

> Any element that claims to represent sound must be driven by real amplitude data. A looping
> fake waveform is worse than no waveform, because users notice.

This sounds like a small aesthetic point. It is not. A fake waveform that keeps animating while
the microphone is muted is a lie the user will catch within ten seconds, and it makes them
distrust everything else on the page — including whether their session is being recorded.

---

## 3. The client island pattern

Next.js App Router defaults to Server Components. The practice room cannot be one: it owns
microphone capture, an AudioWorklet, a WebSocket and playback scheduling — all browser APIs.

The right shape is **one client island**, not client components scattered everywhere:

```
app/app/practice/[sessionId]/page.tsx        Server Component
  └─ fetches session + scenario + persona server-side
  └─ renders <PracticeRoom session={...} />   "use client" — ONE boundary
       └─ everything below here is client
```

Everything that needs the browser lives inside that one boundary. Everything else — history,
reports, the scenario library — stays on the server, where it is faster and simpler.

### State: Zustand, and why not Context

The practice room has state that must be global to the island and changes at high frequency:
turn state, playback position, mic level, caption text, connection status.

React Context re-renders every consumer on every change. At 20 Hz for the mic level, that is a
re-render storm that will make your app janky in a way that is annoying to diagnose.

Zustand lets components subscribe to slices:

```ts
const level = usePracticeStore(s => s.micLevel);   // only re-renders on level change
const state = usePracticeStore(s => s.clientState); // only re-renders on state change
```

The mic meter re-renders 20×/s; the state indicator re-renders three times a minute. That
separation is the entire reason Zustand is here.

**One more thing:** do not put the mic level in React state at all if you can avoid it. The
cleanest version writes the amplitude directly to a CSS custom property or an SVG attribute via
a ref, bypassing React entirely for the 20 Hz path.

---

## 4. The report: synchronisation is the whole trick

Four components must move together:

```
        ┌──────────── waveform (wavesurfer) ────────────┐
        │  ▁▃▅▇▅▃▁▁▃▅▇▇▅▃▁  │ turn boundaries + score markers
        └───────────────┬───────────────────────────────┘
                        │ playhead position (ms)
        ┌───────────────┼───────────────┬───────────────┐
        ▼               ▼               ▼               ▼
   transcript      highlighted      score panel     turn detail
   auto-scroll        turn         active criterion
```

Drag the playhead → the transcript scrolls, the current turn highlights, the score panel
switches to that turn's criteria. Click an evidence span → the audio seeks there. Click a score
marker → everything jumps.

### The architecture that makes this simple

**One source of truth: `playheadMs`.** Everything else derives from it.

```ts
const playheadMs = usePlayerStore(s => s.playheadMs);
const currentTurn = useMemo(
  () => turns.find(t => playheadMs >= t.start_ms && playheadMs < t.end_ms),
  [playheadMs, turns]
);
```

The alternative — each component holding its own notion of "where we are" and syncing via
events — produces drift you will never fully fix. One number, derived views.

**Throttle the writes.** wavesurfer fires `audioprocess` at animation frame rate (~60 Hz).
Writing to the store at 60 Hz and re-rendering a transcript of 200 turns will drop frames.
Throttle store updates to ~10 Hz for scroll-following, and read `currentTime` directly for the
playhead visual. The eye cannot tell the difference; the profiler can.

### wavesurfer.js essentials

- Feed it a **peaks array precomputed server-side**, not the raw audio. Decoding a 20-minute WAV
  in the browser to draw a waveform is a two-second freeze on first render. Compute peaks once
  when the recording is finalised and store them with the session.
- **Regions** mark turn boundaries. **Markers** mark scores. Both are click targets.
- `seekTo` takes a 0–1 progress value, not milliseconds. This trips everyone once.
- Destroy the instance on unmount or you will leak an `AudioContext` per report you open.

---

## 5. Report content: the rules that matter

### Verdict block

Three sentences of summary, then three strengths and three improvements, **each linking into
the moment that justifies it**. No generic encouragement.

"Be more confident" is not feedback. "These three answers opened with a hedge — here they are,
timestamped" is feedback. The difference is that one of them is actionable and the other is a
horoscope.

### Score panel

One row per criterion: score, confidence, a miniature bar against the user's **own** history,
**the rubric anchor text for that value**, and an expander revealing contributing turns.

Showing the anchor text is a small decision with a large effect. The user does not just see
"structure: 3" — they see the sentence that defines a 3, which was written by a human, and read
by the annotator, and used to train the model. It makes the score feel like a measurement
rather than an opinion.

Criteria with insufficient signal read **"not enough signal"**, never a number.

### Colour discipline

Green, amber and red are reserved **exclusively** for rubric values. Slate for
not-enough-signal. Nothing else on the site may use those three colours, ever.

The reason: if red means "weak on this criterion" in one place and "error" in another, the user
has to read context to know which. Reserving them means a colour glance is always meaningful.

And every score is paired with **its numeral and a textual anchor**, so meaning is never
carried by colour alone — which is both an accessibility requirement and just better design.

### The annotation affordance

A discreet per-turn control to record a human score, sitting quietly in the report.

This is how your training set grows without building a separate annotation tool. Every time you
review your own session, you can leave labels. By day 19 you will have a head start on the
1,000 turns you need, collected as a side effect of using the product.

Small feature, disproportionate payoff. Do not cut it.

### Retry one question (RP-08)

Re-run one question in isolation without repeating the whole session. This is the feature that
drives repeat usage: the loop is *practise → see the weak answer → fix that one answer → see it
improve*, and it takes ninety seconds rather than twenty minutes.

---

## 6. Progressive rendering

The coach takes 1–3 minutes on a long session. Do not block the report on it.

```
immediately        transcript, delivery metrics, waveform, session metadata
as scores arrive   score panel rows fill in, one criterion at a time
when narrative is  verdict block appears
   ready
```

Redis pub/sub publishes `report-ready`; the client subscribes and fills in. Skeletons must match
the **final layout dimensions** so nothing jumps when content arrives — layout shift on a page
someone is reading carefully is uniquely irritating.

---

## 7. Design system: four decisions carry the whole impression

The product must look **deliberate rather than templated**. Four choices do most of that work:

1. **Calm, not clinical.** The user is already nervous. Generous line height, restrained
   colour, no red until there is something to say.
2. **Dark-first with a genuine light mode.** Practice happens late at night. "Genuine" means
   actually designed, not inverted.
3. **One accent colour**, with green/amber/red reserved exclusively for rubric values.
4. **The practice room is a different surface entirely.** Everywhere else is a dense data
   application. The practice room is nearly empty.

| Token group | Definition |
|---|---|
| Surfaces | Three elevation levels: page, card, raised. Separation from a 1px border and a subtle background shift — **not shadows**. |
| Typography | One sans family at two weights (regular, medium); one mono family for identifiers and metrics. **Six sizes only:** 12, 13, 15, 17, 22, 32. |
| Score colours | Green strong, amber developing, red weak, slate not-enough-signal. Always paired with numeral + anchor text. |
| Spacing | 4px base scale. Every gap, pad and margin is a multiple. |
| Motion | < 200 ms for state changes, 400 ms for panels. The speaking indicator and the replay playhead are the **only** continuous animations. All motion respects `prefers-reduced-motion`. |
| Icons | One outline set, 16px inline / 20px standalone. |

**Six type sizes only** is the constraint that does the most work. Unlimited sizes is how
interfaces end up looking accidental. Pick six, use six.

---

## 8. Accessibility — a stronger obligation than usual

A product built entirely around speech has an unusually strong obligation here.

- **Full keyboard operation.** Every control reachable and operable without a mouse.
- **ARIA live regions for turn state changes.** A screen-reader user must know it is their turn.
  This is the single most important accessibility feature in the practice room.
- **Visible focus rings.** Do not remove outlines.
- **Captions that satisfy users who cannot hear the persona at all** — which means captions must
  be complete and correctly timed, not decorative.
- **A text-input practice mode is the correct accommodation** for users who cannot speak. It is
  listed as P1 — do not build it now, but do not architect it out either. Keep the turn
  pipeline agnostic about where the user's text came from.
- **Reduced motion:** the amplitude ring degrades to a static state indicator.

---

## 9. Error states, specifically

Distinguish four cases. Each gets a distinct message and a recovery path, never a stack trace.

| Case | What the user sees |
|---|---|
| Microphone denied | **Browser-specific instructions**, because the recovery is buried in settings and differs per browser. This is the one that most needs care. |
| Network failure | Calm reconnection state, automatic retry, session preserved |
| Model unavailable | "Connection trouble" — the session continues degraded, and it says so |
| Not found / not owner | Plain 404, no detail leakage |

Microphone denial deserves the extra effort: in Chrome it is a padlock icon in the address bar;
in Firefox it is a permissions panel; on macOS there is a second OS-level layer. A generic
"please allow microphone access" leaves people stuck.

---

## 10. Pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Client components scattered everywhere | Slow pages, hydration errors | One client island |
| Mic level in React state | Jank at 20 Hz | Ref → CSS variable, bypass React |
| Context instead of Zustand | Re-render storms | Slice subscriptions |
| Decoding audio client-side for the waveform | 2 s freeze on report open | Precompute peaks server-side |
| Playhead updates at 60 Hz into the store | Dropped frames on long transcripts | Throttle to ~10 Hz for derived views |
| Fake waveform | Users notice, trust collapses | Real amplitude only |
| Spinner during `thinking` | Feels like software loading, not a person considering | Subtle pulse |
| Skeletons that don't match final dimensions | Layout shift while reading | Match dimensions exactly |
| wavesurfer not destroyed on unmount | An AudioContext leaked per report opened | Cleanup in `useEffect` return |
| Green/amber/red used elsewhere | Colour stops meaning anything | Reserve them absolutely |

---

## 11. Interview questions this phase earns you

- *How do you keep a 20 Hz meter from re-rendering your React tree?*
- *Your reply takes 1.4 seconds — how does the interface make that feel fast?*
- *How do the waveform, transcript and score panel stay in sync?*
- *Why does the practice room have no navigation?*
- *What happens if someone denies microphone permission?*

---

## 12. Checklist before Phase 4

- [ ] Practice room runs a full live session in the browser, end to end
- [ ] Level meter visible at all times, driven by real amplitude
- [ ] Thinking state appears within 200 ms of endpointing
- [ ] Four client-visible states only; connection loss reconnects calmly
- [ ] `Escape` does not end the session; tab close confirms and flushes
- [ ] Report renders progressively as coach results arrive
- [ ] Synchronised replay: playhead moves transcript, turn highlight and score panel together
- [ ] Click-to-play evidence seeks to the exact moment
- [ ] Annotation control present on every turn
- [ ] Retry-one-question works
- [ ] Reduced motion and keyboard operation verified

→ `phase-4-LEARN.md`
