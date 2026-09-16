# Phase 5 walkthrough — what's built, what's not real yet, and exactly what to do

This document exists because Phase 5 could not be completed for real in the environment this
session ran in — not because the code is missing, but because the two inputs the whole phase is
built on (real recruited-session audio, and a second independent human annotator) don't exist
here. Everything else — every table, script, endpoint, and page the phase doc asks for — is
built, tested, and has been run live against real Postgres at least once. This document is the
bridge between "the infrastructure is real" and "the numbers are real."

Read `docs/RESULTS.md` first. If it says `TODO: measure` next to the human ceiling, nothing in
this project should be described as a completed fine-tune yet — that's not a bug, it's the
honest state, and it's what CLAUDE.md §10 asks for over a fabricated number.

---

## 1. What actually exists right now

**Fully built, tested, and run live against real Postgres this session:**

- `model_versions`, `eval_runs`, `dataset_revisions`, `dataset_members`, `pre_labels`,
  `shadow_scores` tables (migrations `e5f6a7b8c9d0`, `f6a7b8c9d0e1`, `a7b8c9d0e1f2`), including
  the partial unique index that keeps exactly one `active` `model_versions` row per role —
  verified live by trying to insert a second one and watching Postgres reject it.
- `services/training/dataset/build.py` — assembles turns tagged `self`/`recruited`/`synthetic`,
  splits by session and holds out whole speakers (with a documented fallback for <=2 speakers,
  `docs/decisions/0020`), asserts no speaker leaks across splits, and writes a reproducible
  content-hash `dataset_revisions` row. Run twice in a row against the same data, it produced
  the *identical* hash both times.
- `services/training/dataset/synthetic.py` — generates quality-tiered synthetic answers via real
  LLM calls (litellm), capped at <=35% of train / 0% of eval by `split.py`. A real call was made
  and returned a real, on-topic interview question and answer during this session.
- `/admin/annotate/*` (the annotation tool) and `/admin/registry/*` (promote/rollback) — real
  FastAPI endpoints, admin-gated, exercised live: a real queue fetch, a real submission, a real
  double-labelled-item disagreement detected between two accounts, a real 403 for a non-admin.
- `services/training/annotate/iaa.py` — computes real quadratic-weighted-kappa inter-annotator
  agreement from whatever `annotations` rows exist. Run live with two real accounts labelling the
  same item, it computed a real (if statistically meaningless at n=1) kappa.
- `services/training/train.py` — the full ablation ladder (majority-class, ridge-on-deterministic-
  features, frontier zero/few-shot, DeBERTa-v3-base multi-task fine-tune with 3-seed ensembling
  and isotonic calibration, LoRA row). Baselines ran end-to-end live, wrote real metrics to
  Weights & Biases (offline mode) and printed real QWK/MAE numbers. The fine-tune row loads the
  real `microsoft/deberta-v3-base` encoder from Hugging Face and enters the training loop — see
  §5 below for the honest status of a *completed* training run.
- `scripts/eval.py` (`make eval` equivalent) — computes every Task 5.5a metric, refuses to touch
  the test split without `--publish` (verified live: it exits 1 without the flag), and writes
  real `eval_runs` rows.
- `services/training/eval/generate_results.py` — generates `docs/RESULTS.md` from the real
  database, never hand-assembled. Ran live, produced the file you're looking at.
- Shadow mode (`services/coach/app/report/build.py::maybe_run_shadow_scoring`) — wired into the
  real scoring path, writes to the new `shadow_scores` table, sampling logic unit-tested against
  its configured rate.

**What none of the above changes:** the *data* those tools operated on this session was either
(a) whatever incidental real sessions exist from this project's own Phase 0-4 live testing —
essentially zero turns with `training_consent=true`, since dev/test accounts default to
`training_consent=false` — or (b) explicitly-flagged, non-real placeholder data (`--dev-fixtures`,
clearly tagged `@phase5-dev-fixture.invalid`, deleted again after each smoke test) used purely to
prove the code paths execute correctly. **No number produced against that placeholder data is in
this repository's `docs/RESULTS.md` as a final artifact** — the generator was re-run against a
clean database before this phase's work was considered done, so what you'll see there is the
honest "nothing measured yet" state unless you've since run the real pipeline yourself.

---

## 2. Why the data doesn't exist, precisely

1. **Phase 4's Day 17 (recruited sessions) never ran.** `docs/PROGRESS.md`'s own Phase 4 entry
   records this explicitly: "not a coding task, and not executable in this environment... needs
   10-15 real booked participants, a live video/audio call, a person taking notes... did not
   happen and could not happen here." Phase 5's own `docs/phase-5-BUILD.md` closes with: "the most
   valuable output of this phase is not code. It is roughly 400-600 real user turns from eight or
   more speakers, with consent. Phase 5 cannot proceed without them." That prerequisite was never
   met.
2. **A second independent human annotator doesn't exist in this environment.** I (the agent that
   built this) am one model instance. Using myself to produce "two independent human annotations"
   would not measure inter-annotator agreement — it would measure nothing, while looking like it
   measured something. CLAUDE.md §9 is explicit: "the evaluation split is human-labelled only and
   is never shown to any generating model." Fabricating a second rater the same way would violate
   the entire premise the fine-tune's headline claim depends on (`docs/phase-5-LEARN.md` §5's
   "distillation, not agreement with human judgement" trap).

Both are real-world, human-labor prerequisites. No amount of additional engineering in this
session removes them.

---

## 3. Step-by-step: what you need to do to get real results

### 3.1 — Collect real consented data

You don't need a formal "Day 17" event to start — any session where a real user's
`training_consent` is `true` on the `Consent` row qualifies. The fastest paths:

- **Run real practice sessions yourself**, with training consent turned on: Settings > Privacy >
  turn on "training data consent" before starting a session, or pass
  `training_consent: true` explicitly when creating a session via the recruited-session consent
  screen (`StartSessionDialog`'s "this is a recruited/research session" toggle).
- **Recruit a handful of real people** (the original Day 17 plan is still the right shape — 10-15
  people, 5-10 minutes each, consent form first). `docs/phase-4-BUILD.md` TASK 4.6 has the full
  script (three verbatim debrief questions, the "fix only what blocks the next participant" rule).
  You do not need to redo this all at once — even 2-3 real speakers meaningfully improves the
  speaker-holdout split's honesty over the <=2-speaker fallback (`docs/decisions/0020`).
- Set `TRAINING_SELF_USER_EMAIL` in `.env` to your own account's email once you have one — without
  it, `dataset/build.py` guesses ("the earliest-created real user") and warns loudly that it's
  guessing.

### 3.2 — Build the dataset

```bash
uv run --directory services/training python dataset/build.py --synthetic 3
```

`--synthetic 3` generates 3 real synthetic answers per scenario per quality level (1-5) via a
real LLM call — real API cost, capped by `split.py` at <=35% of train and 0% of eval regardless
of how many you generate. Omit it to build only from real consented turns. Never pass
`--dev-fixtures` here — that flag exists only for smoke-testing the pipeline itself and writes
data tagged `@phase5-dev-fixture.invalid` that this walkthrough's own author deleted after every
use.

Read the console output. It tells you, honestly, whether you're anywhere near the ≥1,000-turn,
≥8-speaker targets — it will not pretend you are.

### 3.3 — Get a second annotator and start labelling

```bash
uv run python scripts/grant_admin.py your-email@example.com
uv run python scripts/grant_admin.py a-friends-email@example.com   # the second annotator
```

Both of you sign in and go to `/app/annotate`. `docs/phase-5-LEARN.md` §6: budget 20 minutes of
calibration together first (read the anchor descriptors out loud, agree on borderline cases)
before labelling for real — this materially changes the eventual kappa.

Toggle "Show pre-labels" only once you have a meaningful training split and want to speed up
labelling that split specifically (Task 5.3d) — it is hard-disabled for validation/test items
regardless of the toggle. Pre-labels themselves need to be generated first:

```bash
uv run --directory services/training python annotate/pre_label.py
```

Watch the progress panel at the top of `/app/annotate` — it shows real counts of labelled pairs,
double-labelled-with-two-annotators, and pending adjudications, straight from the database.

### 3.4 — Compute inter-annotator agreement

```bash
uv run --directory services/training python annotate/iaa.py --write-report
```

**Do this before spending more time labelling if the number comes back low.**
`docs/phase-5-BUILD.md` TASK 5.3c, verbatim: "If humans agree at < 0.5 on a criterion, fix the
rubric anchors before training anything." The rubric anchors live in
`content/rubrics/*.yaml` — tighten the vaguest ones and recalibrate before continuing.

### 3.5 — Train

```bash
uv run --directory services/training python train.py --seeds 3 --epochs 4
```

**This is genuinely CPU-heavy.** In this session's own environment (a CPU-only Windows dev
machine), a single seed's forward+backward pass over even a handful of examples did not complete
within several minutes — see §5 below. **Use a free Kaggle or Colab GPU runtime for a real run**
(`docs/phase-5-BUILD.md`'s own acceptance criterion assumes "a free T4," not a CPU laptop). On a
T4, the phase doc's own estimate is under 20-30 minutes for the full ablation ladder.

Set `WANDB_MODE=online` and a real `WANDB_API_KEY` in `.env` first if you want the runs to
actually sync to a dashboard rather than stay local — offline mode (the default here) still logs
everything, just not to the cloud.

`--skip-frontier` avoids the real LLM calls rows 3/4 make — leave it off for a real run; those
rows are "the real baseline to beat" (Task 5.4a), and skipping them only saves API cost.

### 3.6 — Evaluate for real, and publish

```bash
uv run python scripts/eval.py --split validation                     # routine checks, unlimited
uv run python scripts/eval.py --split test --publish --seed 0        # the real reporting number
```

Every `--publish` call against the test split is logged (console + `eval_runs.published=true`) —
this is deliberate friction, not a bug. Don't `--publish` casually; it's meant to happen once,
when you're ready to report a real number.

### 3.7 — Generate the real results table

```bash
uv run --directory services/training python eval/generate_results.py
```

Overwrites `docs/RESULTS.md` from the database. If a row still says `TODO: measure`, that
ablation row hasn't been run and published yet — the generator will never fill it in with a
guess.

### 3.8 — Promote, if it earns it

```
POST /admin/registry/promote   { "candidate_version_id": "<uuid>" }
```

(Admin-only, same bearer token as `/admin/annotate`.) This only succeeds if every one of the
candidate's published test-split seed kappas individually beats the current active version's —
"not on one lucky run" (Task 5.5c). If it's rejected, the response tells you which seeds fell
short. Rollback (`POST /admin/registry/rollback`) is unconditional — it's an operator override,
not a re-litigation of the numbers.

### 3.9 — Shadow mode is already running

`services/coach`'s `shadow_sample_rate` defaults to 0.10 — 10% of every real turn scored from
now on also gets a second, independent score written to `shadow_scores` (never shown to users).
No action needed; once real traffic flows, query that table against `turn_scores` to see the
comparison drift over time (Task 5.5d's actual point — "a live measurement, not a historical
one").

---

## 4. Real problems this session hit and fixed while proving the pipeline works

- **DeBERTa-v3's tokenizer needs `sentencepiece` explicitly** — the `transformers` library's
  fallback tiktoken-based conversion path cannot parse its `spm.model` file at all and fails with
  an opaque `ValueError`. Added as an explicit dependency
  (`services/training/pyproject.toml`) after hitting this live.
- **Hugging Face Hub caching degrades to non-symlink mode on Windows** without Developer Mode or
  admin — harmless (just uses more disk), but expect the warning.
- **CPU-only DeBERTa-v3-base training is slow enough to matter** on constrained hardware — see §5.
  This is the same category of finding Phase 1 recorded for Piper's cold-start latency and
  Phase 2 recorded for `faster-whisper`'s CPU inference time: real, measured, and a genuine
  argument for using a GPU runtime rather than a local CPU machine for this specific step.

## 5. Honest status of the fine-tune training loop specifically

The training script was run live, twice, against real (synthetic + placeholder) data on this
session's CPU-only environment. Both times: the dataset loaded correctly, the leakage assertion
passed, `microsoft/deberta-v3-base` downloaded and loaded correctly (confirmed via a real
Hugging Face Hub call and a successful weight-load report), and the training loop was entered.
Neither run completed a full forward+backward pass within the time available in this session —
CPU inference/training for a 184M-parameter transformer with disentangled attention is
substantially slower than this environment's already-established baseline for smaller models
(Phase 1/2's notes on Whisper/Piper CPU latency). A standalone tensor-shape/forward-pass check
(`model.py`'s `MultiCriterionScorer`, exercised directly rather than through the full
orchestration) confirmed the architecture is wired correctly — inputs, aux features, and outputs
all have the expected shapes — but did not itself confirm a completed backward pass and weight
update within this session's time budget either.

**What this means concretely: the training *code* is verified correct by construction and by
partial live execution; a complete training run producing a real trained checkpoint was not
achieved in this session.** Run `train.py` on a GPU runtime (Kaggle/Colab, per §3.5) to get an
actual trained model — the code does not need to change to do this, only the hardware it runs on.
