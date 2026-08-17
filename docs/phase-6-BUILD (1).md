# Phase 6 — BUILD — Proof and polish (days 22–24)

Build specification for Claude Code. Read `CLAUDE.md`, `docs/13-observability.md`,
`docs/16-evaluation.md` and `docs/18-deployment.md` first.

**Exit criterion:** observability and evaluation surfaces, a landing page with published
numbers, a self-host path, a deployed instance, a model-free demo path, and a recorded
three-minute walkthrough.

---

## TASK 6.1 — Observability page (`/app/observability`, admin)

Ordered top to bottom exactly as below. **The latency header is first because that is the
number the project is about.**

### 6.1a — Latency header

- End-of-speech → first-audio at **p50, p90 and p95**, over a selectable window.
- **The target line (1400 ms p95) is drawn on the chart.** A chart without the line is data; a
  chart with it is an argument.
- Filterable by date range, scenario family and host class.

Query the **end-to-end distribution directly** from `latency_events` where `stage = 'e2e'`.
**Do not sum per-stage percentiles** — percentiles do not add, and the sum over-provisions.

### 6.1b — Stage breakdown

Median and p95 per stage, **stacked so the dominant contributor is visually obvious within two
seconds.** Fixed stage order matching the pipeline order, not alphabetical.

### 6.1c — Turn waterfall

Select one turn → expand stage by stage with **its prompt, its response and its audio
attached.** This is how the slow component is found, and it is the most persuasive element on
the page.

Requirements:
- Horizontal bars proportional to duration, absolute ms labels.
- Click a stage → see the associated `model_calls` row if any.
- Inline audio playback of that turn's user utterance and persona reply (persona audio
  regenerated from transcript + voice id).

### 6.1d — Model call table

Every invocation: role, model, prompt version, tokens in/out, TTFT, total latency, cost,
**cache status**. Filterable and sortable. The cache column proves prefix caching is actually
hitting — otherwise that is an unverifiable claim.

### 6.1e — Cost panel

Spend per session, per user and per month, **beside the counterfactual figure had every score
come from a frontier model.**

```sql
-- actual
SELECT SUM(cost_cents) FROM model_calls WHERE session_id = :id;
-- counterfactual: every turn_score priced at the frontier rate for that criterion
```

**That comparison is the economic argument for the entire training effort.** Display both
figures and the ratio.

### Acceptance criteria

- [ ] Latency header queries `stage = 'e2e'` directly, with the target line drawn
- [ ] Stage breakdown stacked in pipeline order
- [ ] Waterfall shows prompt, response and playable audio per stage
- [ ] Model call table shows cache status and is filterable
- [ ] Cost panel shows actual, counterfactual and ratio
- [ ] Page loads in < 2 s over 10,000 latency events (indexes verified with `EXPLAIN`)

---

## TASK 6.2 — Evaluations page (`/app/evals`, admin)

- **Model registry** — every scorer version with base model, adapter, dataset revision, headline
  metrics, status. **Promotion and rollback happen here**, as status changes, with confirmation.
- **Suite results** — agreement, error, calibration and cost, with a **per-case grid linking
  each cell to the turn, the human label and the disagreement.** Sort by disagreement magnitude
  descending by default — the interesting cases first.
- **Regression chart** — metrics across model and prompt versions over time, **with deployment
  markers**.
- **Comparison view** — two versions over identical cases, **disagreements surfaced first**.
- **Speech component panel** — WER, endpointing precision and recall, RTF by host class.

### Acceptance criteria

- [ ] Registry lists all versions; promotion and rollback work and are status changes only
- [ ] Per-case grid links each cell to the turn, its human label and the model's score
- [ ] Grid defaults to sorting by disagreement magnitude
- [ ] Regression chart shows deployment markers
- [ ] Comparison view shows disagreements first

---

## TASK 6.3 — Level 1 and Level 2 evaluation suites

Phase 5 built Level 3. These two remain.

### 6.3a — Level 1: speech components (`make eval-speech`)

| Metric | Requirement |
|---|---|
| Word error rate | Against a fixed fixture set **including accented speech and technical vocabulary** |
| Real-time factor | Per host class. **Above 1.0 the design fails** — the suite must fail, not warn |
| Endpoint precision | Of ends called, fraction where the speaker had genuinely finished |
| Endpoint recall + latency | Against the ≥200 hand-marked boundaries from day 5 |
| Time to first audio | p50/p90/p95 — the headline product metric |
| Synthesis RTF | Whether TTS outruns playback |

Fixtures committed in `tests/fixtures/audio/`. The suite must be deterministic and runnable in
CI.

### 6.3b — Level 2: persona adherence (`make eval-persona`)

| Metric | Requirement |
|---|---|
| **Character break rate** | A judge model scans transcripts for coaching, grading, praise or rubric disclosure. **Target zero.** Any non-zero result fails the suite. |
| Question repetition | Semantically duplicate questions within a session, by embedding similarity |
| Plan adherence | Planned topics covered within the target duration |
| Turn length distribution | **A creeping mean is an early warning of prompt drift** — chart it across versions |
| **Difficulty separation** | Follow-up rate, acknowledgement length and interruption count across tiers. **If gentle and hard are statistically indistinguishable, fail the suite** — the ladder is decorative and that is a defect. |
| Safety suite | The Phase 2 suite, run here too, against both hosted and local persona models |

Difficulty separation requires a statistical test, not eyeballing: run N sessions per tier
against fixture inputs and assert a significant difference on each of the three behavioural
measures.

### 6.3c — Nightly CI evaluation (OE-13)

A scheduled workflow runs all three levels and posts metrics. **A regression is caught by the
repository, not by a user.** Failures open an issue automatically.

### Acceptance criteria

- [ ] `make eval-speech` runs deterministically from committed fixtures
- [ ] RTF > 1.0 fails the suite rather than warning
- [ ] `make eval-persona` reports all six metrics
- [ ] Character break rate is zero; a deliberately broken prompt makes it non-zero (test the test)
- [ ] Difficulty separation is statistically asserted, not eyeballed
- [ ] Nightly workflow runs and posts metrics

---

## TASK 6.4 — Production Dockerfiles and deployment

### 6.4a — Multi-stage builds

One Dockerfile per service. Requirements:

- Builder stage installs dependencies with `uv sync --frozen --no-dev`; runtime stage copies
  only the resulting virtualenv.
- **Layer order by change frequency:** dependency files first, source last.
- **Model weights are NOT baked into the image.** Downloaded on first boot into a cache volume,
  or mounted. Baking a 150 MB model means re-pushing it on every code change.
- Non-root user. Explicit `HEALTHCHECK`.
- Target: `api` and `coach` images < 400 MB; `realtime` < 800 MB excluding model weights.

### 6.4b — Stateful deployment requirements for `realtime`

- **Session affinity.** A session is pinned to one process. Document explicitly that a naive
  round-robin balancer breaks reconnection.
- **Explicit concurrency cap** (`MAX_CONCURRENT_SESSIONS`). At capacity, refuse the upgrade
  with a clear **"at capacity, try again shortly"** message — **never crash, never queue
  silently.**
- **Health checks:** liveness must **not** touch the models (a slow model load must not read as
  a dead process); readiness must confirm models are resident.
- **Graceful shutdown on SIGTERM:** stop accepting new sockets, allow active sessions to finish
  or finalise them, flush all uploads, then exit. A deploy that drops five live sessions is a
  bad deploy.
- **Memory sizing documented:** base + ASR (~150 MB) + Piper voices (~60 MB each) + per-session
  buffers.

### 6.4c — Hosting

- **Hugging Face Spaces, Docker SDK, free CPU tier** for `realtime` and `coach` — the only free
  tier with enough resident memory for Whisper and Piper simultaneously.
- **Vercel** for `web`. **Neon** for Postgres. **Upstash** for Redis. **Supabase Storage or R2**
  for objects.
- Fallback documented: run locally, expose via **Cloudflare Tunnel**.
- Production env vars documented in `docs/18-deployment.md` with a checklist, including the
  **second** OAuth app per provider with production callback URLs.

### 6.4d — Self-host path (AS-12)

A single `docker compose up` brings the whole stack online with **local models and no external
dependency** — Ollama for the persona, local faster-whisper and Piper, local Postgres/Redis/
MinIO. Verified from a clean clone on a machine that has never run the project.

### Acceptance criteria

- [ ] All images build; size targets met
- [ ] Weights are not in any image layer (verified with `docker history`)
- [ ] SIGTERM drains active sessions and flushes uploads before exit
- [ ] At-capacity returns a clear message, not a crash
- [ ] Liveness passes while models are still loading; readiness does not
- [ ] Self-host compose works from a clean clone with **zero** external API keys
- [ ] Deployed instance reachable and completes a real session

---

## TASK 6.5 — The model-free demo path ⚠️ ONE HOUR, HIGH VALUE

`/demo` — a pre-recorded sample session that needs **no models running at all.**

- Static JSON + static audio committed to the repo: transcript, turn boundaries, scores,
  evidence spans, delivery metrics, waveform peaks.
- Rendered by **the real report components**, not a mock — so it stays accurate as the report
  evolves, and so what a visitor sees is genuinely the product.
- A guided ~60-second playthrough: play the exchange, then jump to the report and highlight one
  evidence span.
- **No account required. No cold start. Works with every backend service asleep.**

> **Free hosting sleeps.** A recruiter clicking your link at 3 a.m. will otherwise wait through
> a Whisper model load. This is one hour of work and it is what the link actually needs to
> survive.

### Acceptance criteria

- [ ] `/demo` renders fully with `api`, `realtime` and `coach` **all stopped**
- [ ] It uses the real report components, not a mock
- [ ] No authentication required
- [ ] Loads in < 2 s cold

---

## TASK 6.6 — Landing page

Audience: someone who arrived from a link and will decide in **eight seconds**. Job: **prove it
works, not describe it.**

1. **Hero** — outcome headline, one supporting sentence, two actions: *Try a 60-second session*
   (→ `/demo`) and *View on GitHub* with a live star count. **No signup to reach the demo.**
2. **Audio proof strip** — a real recorded exchange, playable inline, **with the latency figure
   shown against each turn.** The claim is a latency claim and audio is the only honest way to
   support it. **This element does more conversion work than everything below it.**
3. **How it works** — three panels with real screenshots.
4. **The two-agent diagram** — where technical readers decide the project is real.
5. **Evaluation callout** — agreement numbers and latency percentiles stated plainly, **with the
   human ceiling beside the kappa.**
6. **Self-host block** with a copyable compose command.
7. Footer.

### Acceptance criteria

- [ ] Lighthouse performance ≥ 90
- [ ] Audio proof strip plays without signup and shows per-turn latency
- [ ] Every published number is **real** and carries its date and model version
- [ ] Two-agent diagram is an actual diagram, not a bullet list
- [ ] Copy command is one click

---

## TASK 6.7 — README and documentation

### README structure

1. One-sentence description + **the demo video embedded at the top**
2. The two-agent diagram
3. **Published metrics** — latency percentiles and scorer agreement **with the human ceiling**
4. **The full results table** from `docs/RESULTS.md`, all eight ablation rows
5. **Where the scorer is weakest**, with worked failure cases
6. Architecture, briefly, linking to `docs/`
7. Self-host — one `docker compose up`
8. **Roadmap** — this is where the 112-feature catalogue belongs: P1 and P2 as a credible
   roadmap, not an unfinished backlog
9. Safety and privacy — including the distress rule and the **honest PII scrubbing limitations**

### Non-negotiable rules

- **Every figure carries its dataset revision, model version and date.** Numbers without
  provenance are marketing.
- **Publish the failures.** A README showing where the scorer is weakest is far more convincing
  than one showing only the headline.
- **Never write a number that was not measured.** If a metric is unavailable, write
  `not yet measured` — never a plausible placeholder that could survive into a published
  document.
- **The product must never imply it predicts hiring outcomes.** It measures performance against
  a rubric the author wrote, and the README and the interface both say so.

### Acceptance criteria

- [ ] Every metric in the README is traceable to an `eval_runs` row
- [ ] The failure-cases section exists with real examples
- [ ] Self-host instructions verified from a clean clone by following them literally
- [ ] `docs/` complete; `docs/decisions/` populated
- [ ] No placeholder numbers anywhere in the repository

---

## TASK 6.8 — Recorded demo

Three minutes. Rehearsed until the pauses are deliberate.

| Beat | Time | Content |
|---|---|---|
| 1. Setup | 15 s | One sentence. Scenario card selected. No architecture yet. |
| 2. The conversation | 60 s | **Live, unedited, real audio.** Answer deliberately badly; let the follow-up land. **Do not cut.** |
| 3. Pressure beat | 20 s | Ramble at hard difficulty; persona interrupts or goes silent. |
| 4. The report | 40 s | Click one evidence span; the audio plays that exact moment. **Say nothing over it.** |
| 5. Architecture | 20 s | Two-agent diagram. Persona on the latency path, coach off it, and why. |
| 6. **The close** | 25 s | Observability + evaluations. State the latency percentiles and the scorer agreement **against the human ceiling** out loud, regression chart on screen. |

**If thirty seconds must be cut, cut beat 3. Never beat 6.**

### Acceptance criteria

- [ ] Under 3:15 total
- [ ] Beat 2 is genuinely uncut, real audio
- [ ] Beat 4 has no voiceover
- [ ] Beat 6 states real numbers with the ceiling
- [ ] Linked from the README and the landing page

---

## Phase 6 definition of done — and the project is complete when

- [ ] Observability page: latency header with target line, stage breakdown, waterfall, model
      calls, cost counterfactual
- [ ] Evaluations page: registry, suite results, per-case grid, regression chart, comparison
- [ ] Level 1 and Level 2 suites running, nightly CI posting metrics
- [ ] Difficulty separation statistically asserted; character break rate zero
- [ ] Production images built; stateful deployment with graceful shutdown and capacity limits
- [ ] Self-host verified from a clean clone with zero external keys
- [ ] **`/demo` works with every backend service stopped**
- [ ] Landing page with the audio proof strip and real published numbers
- [ ] README with metrics, the full results table and the failure cases
- [ ] Three-minute demo recorded
- [ ] Resume and skills section rewritten with real numbers
- [ ] `docs/decisions/` populated

> **The eight things that define done** (from `00-START-HERE.md`): streaming voice loop inside
> the budget · adaptive endpointing tuned against hand-marked boundaries · explicit turn state
> machine with a degraded state · persona with a question plan and three difficulty tiers ·
> coach with evidence spans and confidence gating · synchronised report replay · human-labelled
> evaluation set with published agreement · fine-tuned scorer benchmarked against a prompted
> baseline.
>
> If all eight are true and every number is real, the project is finished.
