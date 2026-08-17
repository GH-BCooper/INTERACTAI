# Phase 6 — LEARN — Proof and polish (days 22–24)

**Exit criterion:** observability, landing page, documentation, deployment and a recorded demo.

**Study time this phase:** ~7 hours — stateful deployment 3h, Langfuse 4h (droppable — first on
the cut list).

This is the phase that converts three weeks of work into something a stranger can evaluate in
three minutes.

---

## 1. This phase is not polish

It is tempting to treat days 22–24 as tidying up. They are not.

**Everything before this is a demo that a capable developer could assemble in a month.** The
observability and evaluation pages are what say you understand that you built **two
non-deterministic systems and measured both of them.** That is the differentiator, and it only
exists if you build the surfaces that show it.

If you must cut thirty seconds from the demo, cut the pressure beat. **Never cut the close.**

---

## 2. Observability: three questions the page must answer

The page exists to answer, in order:

1. **How fast is it really?**
2. **Which stage is the problem?**
3. **What did the fine-tune actually save?**

### Latency header — the number the project is about

End-of-speech to first-audio at **p50, p90 and p95, with the target line drawn on the chart**,
at the very top of the page.

Drawing the target line matters more than it sounds. A chart with a line at 1400 ms and a p95
below it is an argument. A chart without the line is just data.

### Stage breakdown

Median and p95 per stage, **stacked so the dominant contributor is obvious**. The reader should
be able to point at the biggest block within two seconds.

### The turn waterfall

One turn expanded stage by stage, with **its prompt, response and audio attached**.

This is how you find the slow component, and it is also the single most impressive thing on the
page to an engineer. Being able to click one turn and see exactly where 1,043 ms went — with the
audio right there — is the difference between claiming instrumentation and having it.

### Model call table

Every invocation with role, model, prompt version, tokens, TTFT, cost and **cache status**. The
cache column is doing real work: it proves your prefix caching is actually hitting, which is
otherwise an unverifiable claim.

### Cost panel — the economic argument

Spend per session and per month, **beside the counterfactual figure had every score come from a
frontier model.**

That comparison is **the economic argument for the entire training effort**. It converts "I
fine-tuned a model" into "I fine-tuned a model and it costs 1/20th as much, here is the
number." Build it — it is a `SUM` over `model_calls` with a multiplier, and it carries
disproportionate weight.

---

## 3. The evaluations page

- **Model registry** — every trained scorer version with base model, adapter, dataset revision,
  headline metrics and status. Promotion and rollback happen here.
- **Suite results** — agreement, error, calibration and cost, with a **per-case grid linking
  each cell to the turn, the human label and the disagreement.**
- **Regression chart** — metrics across model versions over time **with deployment markers**.
- **Comparison view** — two versions over identical cases, **disagreements first.**
- **Speech component panel** — word error rate, endpointing precision and recall, real-time
  factor by host class.

The per-case grid is the one to invest in. *"Show me a case your scorer gets wrong and explain
why"* is a question you will be asked, and being able to click through to it live is a
completely different answer from describing one from memory.

---

## 4. Level 1 and Level 2 evaluation: the suites you have not built yet

Phase 5 built Level 3 (the scorer). Two levels remain, and conflating the three is the most
common way a voice-plus-LLM project ends up unable to say anything precise about itself.

### Level 1 — speech components

| Metric | Why it matters |
|---|---|
| Word error rate on a fixed fixture set, **including accented speech and technical vocabulary** | Everything downstream inherits these errors |
| Real-time factor per host class | **Above 1.0 the design fails** |
| Endpoint precision and recall against your ≥200 hand-marked boundaries | Low precision = cutting people off, the worst subjective failure |
| **Time to first audio at p50/p90/p95** | The headline product metric |
| Synthesis real-time factor | If TTS cannot outrun playback, audio stutters regardless of everything else |

### Level 2 — the persona

Believability is hard to measure, so **measure what is checkable** rather than pretending:

- **Character break rate** — a judge model scans transcripts for coaching, grading, praise or
  rubric disclosure. **Target zero.**
- **Question repetition** by embedding similarity within a session.
- **Plan adherence** — planned topics covered within the target duration.
- **Turn length distribution** — **a creeping mean is an early warning of prompt drift.**
- **Difficulty separation** — follow-up rate, acknowledgement length and interruption count
  across tiers. **If gentle and hard are statistically indistinguishable, the ladder is
  decorative.**
- **Safety suite in CI** — injection, distress, discriminatory-scenario refusal, rubric fishing.

Difficulty separation is the one to run first. You built the parameters in Phase 2 believing
they would change behaviour; this is where you find out whether they did.

---

## 5. Deploying a stateful service

The realtime service **cannot be serverless.** It holds an open socket, a growing audio buffer,
a resident 150 MB ASR model with decoder state, and a state machine. None of that survives a
function invocation boundary.

### Consequences

- **Sticky sessions or session-aware routing.** A session is pinned to one process; a
  round-robin load balancer will break it on the first reconnect.
- **Resident model memory.** Sizing is `base + (ASR model + Piper voices) + per-session
  buffers`. Whisper `base.en` int8 is ~150 MB, Piper ~60 MB per loaded voice. Cap concurrent
  sessions explicitly and return a clear **"at capacity"** message rather than crashing.
- **Health checks that mean something.** Liveness must not touch the models (or a slow load
  looks like a dead process). Readiness must confirm the models are resident.
- **Graceful shutdown.** On SIGTERM: stop accepting new sockets, let active sessions finish or
  finalise them, flush uploads. A deploy that drops five live sessions is a bad deploy.

### Hosting

**Hugging Face Spaces (Docker SDK, free CPU tier: 2 vCPU / 16 GB)** is the only genuinely free
option with enough resident memory for Whisper *and* Piper. Render's free instance is too small.

Fallback: run locally and expose through a **Cloudflare Tunnel** for the demo. This is not a
compromise worth being embarrassed about — it is a documented fallback in a zero-cost design.

---

## 6. The cold-start problem, and the one hour that fixes it

**Free hosting sleeps.** A recruiter clicking your link at 3 a.m. will wait through a cold start
that loads a Whisper model. Many will not wait.

Two mitigations, both required:

1. **The recorded demo video in the README** — which is what most people watch anyway.
2. **A model-free `/demo` path**: a pre-recorded sample session — audio, transcript, scores,
   synchronised replay — that needs **no models running at all.** Pure static data rendered by
   the real report component.

> This is **one hour of work and it is what your link actually needs to survive.**

It is also strictly better than a live demo for a first impression, because it always works,
always sounds good, and shows the report — which is the part that takes 40 seconds to appreciate
and 15 minutes to reach live.

---

## 7. The landing page

Audience: someone who arrived from a link and will decide in **eight seconds**. Job: **prove the
thing works, not describe it.**

- **Hero** — outcome headline, one supporting sentence, two actions: *Try a 60-second session*
  and *View on GitHub* with a star count. **No signup to reach the demo.**
- **Audio proof strip** — a real recorded exchange, playable inline, **with the latency figure
  shown against each turn.** The claim is a latency claim, and **audio is the only honest way to
  support it.** This element does more conversion work than everything below it.
- **How it works** — three panels with real screenshots.
- **The two-agent diagram** — where technical readers decide the project is real.
- **Evaluation callout** — agreement numbers and latency percentiles stated plainly. Competitors
  avoid publishing these; publishing them is the differentiator.
- **Self-host block** with a copyable compose command.

---

## 8. The README

The README is read more than the code. Structure it as:

1. **What it is**, in one sentence, plus the demo video embedded at the top.
2. **The two-agent diagram.**
3. **Published metrics** — latency percentiles and scorer agreement **with the human ceiling**.
4. **The results table** from `docs/RESULTS.md`, all eight ablation rows.
5. **Where the scorer is weakest**, with worked failure cases.
6. **Architecture**, briefly, with links to `docs/`.
7. **Self-host** — one `docker compose up`.
8. **The roadmap** — this is where the 112-feature catalogue finally belongs. P1 and P2 as a
   credible roadmap, not a backlog you failed to finish.
9. **Safety and privacy**, including the distress rule and the PII limitations, stated honestly.

### Publish the failures

> A README that shows where the scorer is weakest is **far more convincing** than one that shows
> only the headline.

This feels counterintuitive and it is correct. Anyone can post a good number. Posting a good
number *plus* an honest account of where it breaks down signals that the number was measured
rather than selected.

Every figure carries its **dataset revision, model version and date**. Numbers without
provenance are marketing.

---

## 9. The demo script — three minutes, rehearsed

| Beat | Time | Content |
|---|---|---|
| **1. Setup** | 15 s | One sentence: what this is and who for. Show the scenario card being selected. **Say nothing about architecture yet.** |
| **2. The conversation** | 60 s | **Live, unedited, real audio.** Let the persona ask a question, answer it **deliberately badly**, let the follow-up land. **Do not cut this section.** |
| **3. The pressure beat** | 20 s | Ramble slightly at hard difficulty; let the persona interrupt or go silent. This is the moment viewers remember. |
| **4. The report** | 40 s | Click one evidence span; let the audio play the exact moment the score came from. **Say nothing over it** — the synchronisation speaks for itself. |
| **5. Architecture** | 20 s | The two-agent diagram. State plainly that the persona is on the latency path and the coach is not, and why. |
| **6. The close** | 25 s | Observability and evaluations pages. State the latency percentiles and the scorer agreement **against the human ceiling** out loud, with the regression chart on screen. |

### Why beat 2 must be uncut

**The single most persuasive thing in the entire demo is an uncut exchange where the reply
arrives fast enough to feel like a person.** Every cut you make invites the suspicion that you
cut out a four-second pause. One continuous minute removes that suspicion entirely.

### Why beat 6 is the one that gets you hired

Everything before it is a demo a capable developer could assemble in a month. The evaluation
page is what says you understand you built two non-deterministic systems and measured both.

**If you must cut thirty seconds, cut the pressure beat. Never the close.**

---

## 10. Portfolio framing

### Resume entry — replace bracketed figures with your real ones

```
InteractAI — Real-Time Multi-Agent Voice Simulator | Open Source

• Built a real-time spoken conversation system with a [1.1]s median and [1.4]s p95
  end-of-speech to first-audio latency, using streaming VAD, ASR, LLM and TTS with
  incremental sentence chunking and adaptive endpointing.
• Designed a two-agent architecture separating an on-path conversational persona from
  an off-path evaluator, allowing each to be optimised and measured against opposed
  objectives.
• Fine-tuned a rubric-scoring model on [1,000] turns with [6,200] human labels,
  reaching [0.71] quadratic weighted kappa against expert raters (human ceiling
  [0.78]) versus [0.52] for a prompted frontier baseline, at [1/20]th the cost and
  [1/10]th the latency.
• Engineered the supporting platform in Python and TypeScript — stateful WebSocket
  session service, queue-driven scoring workers, object-storage audio artefacts, and
  per-stage latency instrumentation exposed as a live percentile dashboard.
```

### Skills section

Your current section lists LLM Fine-Tuning, WebSockets and Docker (basics) with **no project
evidencing any of them.** Once this exists, all three become defensible and three new categories
can be added. **Delete the parenthetical hedges — you no longer need them.**

| Category | Contents |
|---|---|
| **AI engineering** *(new)* | Multi-agent orchestration, structured outputs, context management and compaction, prompt caching, model routing, latency-constrained inference design |
| **Speech and real-time** *(new)* | Streaming ASR, VAD, endpointing, streaming TTS, WebSocket audio transport, jitter buffering, turn-taking state machines |
| **Model training** *(new)* | Dataset construction and annotation protocols, inter-annotator agreement, LoRA and encoder fine-tuning, ordinal regression, calibration, ablation design |
| **LLMOps** *(new)* | Evaluation design, LLM-as-judge, tracing and observability, prompt versioning, cost attribution, regression benchmarking |
| Backend | Python, FastAPI, async architecture, WebSockets, job queues, SQLAlchemy, PostgreSQL, Redis, S3-compatible storage |
| Frontend | React, Next.js App Router, TypeScript, Tailwind, Web Audio API, TanStack Query, Zustand |
| Infrastructure | Docker, Compose, GitHub Actions, stateful service deployment, Sentry, Prometheus |

### The ten interview questions — prepare a specific, concrete answer to each

1. Walk me through your latency budget. Which stage dominated, and what did you do about it?
2. Why is the end-to-end p95 lower than the sum of the per-stage p95s?
3. How do you decide the user has finished speaking, and what happens when you get it wrong in
   each direction?
4. Why fine-tune at all when you could prompt a frontier model?
5. How did you avoid measuring distillation instead of human agreement?
6. What is your inter-annotator agreement, and what does that tell you about your rubric?
7. Show me a case your scorer gets wrong and explain why.
8. Why are the persona and the coach separate systems?
9. What happens when the ASR mishears a technical term mid-answer?
10. What did you do about the fact that your product deliberately puts anxious people under
    pressure?

Questions 5, 6, 7 and 10 are where most candidates run out of depth. They are also the ones
this project is specifically designed to let you answer well.

---

## 11. `docs/decisions/` — the file that writes your interview answers

When a specification choice turned out to be wrong — and several will have — write a short note
in `docs/decisions/`. What you assumed, what happened, what you changed.

These notes are the raw material for every question above, and they are **far more convincing
than a plan that pretended to be right from the start.** "I assumed a fixed 500 ms endpointing
threshold would be fine; it cut off two of my ten test users; here is what I changed and here
is the precision number before and after" is a better answer than any amount of architecture
description.

If you have not been writing them, spend an hour on day 24 reconstructing them honestly. Mark
them as reconstructed.

---

## 12. Checklist — the project is done when

- [ ] Latency dashboard with the target line drawn, at the top of the page
- [ ] Turn waterfall with prompt, response and audio attached
- [ ] Model call table with cache status; cost panel with the frontier counterfactual
- [ ] Evaluations page: registry, suite results, per-case grid, regression chart, comparison view
- [ ] Level 1 speech suite: WER, RTF, endpoint precision/recall, TTFA percentiles
- [ ] Level 2 persona suite: character breaks (target zero), repetition, plan adherence,
      **difficulty separation**
- [ ] Nightly CI evaluation run posting metrics
- [ ] Landing page with the audio proof strip and published numbers
- [ ] README with metrics, the results table, **and the failure cases**
- [ ] `docker compose up` self-host path verified from a clean clone
- [ ] Deployed, with graceful shutdown and an "at capacity" message
- [ ] **The model-free `/demo` path works with everything asleep**
- [ ] Three-minute demo recorded, rehearsed, uncut in beat 2
- [ ] Resume and skills section rewritten with **real** numbers
- [ ] `docs/decisions/` populated

---

## 13. One last thing

Go back to `00-START-HERE.md` §7 and read the sentence this project was designed to earn. Then
say it out loud with your actual numbers in it.

If the numbers are real and you can defend every one of them, you are done.
