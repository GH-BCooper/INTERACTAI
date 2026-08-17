# Phase 5 — BUILD — Dataset and the fine-tune (days 18–21)

Build specification for Claude Code. Read `CLAUDE.md`, `docs/14-dataset.md`,
`docs/15-finetune.md` and `docs/16-evaluation.md` first.

**Exit criterion:** a trained, calibrated scorer deployed with published metrics against a
human-labelled held-out set, and the full ablation ladder in a results table.

**This is the technical centre of the project.** The rules in this file about split hygiene and
label provenance are not stylistic — violating them makes the headline claim invalid.

---

## TASK 5.1 — Additional tables

Now add the three tables deferred from Phase 0.

```
model_versions   role, name, base_model, adapter_key, trained_on_dataset,
                 metrics JSONB, status ∈ {training, candidate, active, retired},
                 seed_count, dataset_revision_hash
eval_runs        suite, model_version_id, prompt_version, qwk, mae, spearman,
                 adjacent_accuracy, ece, false_alarm_rate, mean_cost, seed,
                 dataset_revision_hash, split ∈ {validation, test}
dataset_revisions hash, created_at, turn_count, label_count, source_breakdown JSONB,
                 excluded_turn_ids JSONB, notes
```

**Constraint:** exactly one `model_versions` row per role may have `status = 'active'`. Enforce
with a partial unique index — not application logic.

### Acceptance criteria

- [ ] Migration applies cleanly
- [ ] Partial unique index prevents two active versions for one role
- [ ] `eval_runs` records the dataset revision hash — a row without one is rejected

---

## TASK 5.2 — Dataset construction (day 18)

### 5.2a — Collection

`services/training/dataset/build.py` assembles turns from three sources with a `source` tag:

| Source | Tag | Notes |
|---|---|---|
| Own sessions | `self` | Highest fidelity, one speaker |
| Recruited sessions | `recruited` | **Only where `training_consent = true`** |
| Synthetic | `synthetic` | Generated at instructed quality levels |

**Hard requirement:** turns flagged `training_excluded` (consent revoked) are filtered out at
build time, and the exclusion is recorded in `dataset_revisions.excluded_turn_ids`.

### 5.2b — Synthetic generation

Fills the **tails of the distribution, which real data never provides** — most real answers are
mediocre; almost none are terrible or excellent.

- For each scenario question, generate answers at instructed quality levels 1 through 5:
  *"Answer this question as a nervous candidate who gives no concrete detail"* (level 1),
  through to *"…as a strong candidate with a clear arc and specific numbers"* (level 5).
- **The instructed level is a generation parameter, not a label.** Synthetic turns are labelled
  by humans like everything else. Do not shortcut this.
- Generate with **varied phrasing, length and filler density** so the model does not learn "the
  synthetic style" as a shortcut feature.
- **Cap synthetic at ≤ 35% of the training split**, and **0% of the evaluation split.**

### 5.2c — Splits ⚠️ THE CRITICAL PART

```python
def split_dataset(turns) -> tuple[Train, Val, Test]:
    """Split by SESSION, and hold out entire SPEAKERS where possible.
    NEVER split by turn."""
```

- Group by `session_id`, then by speaker. Assign whole sessions to splits.
- **Hold out entire speakers for the test split** wherever speaker count allows.
- Target 70 / 15 / 15 by turn count, achieved by assigning whole sessions.
- **Write an assertion that fails the build if any speaker appears in more than one split.**
  This is not a warning — it is a build failure.
- Stratify by criterion score distribution so all splits span the scale.

> Turns from one session share a speaker, nerves, vocabulary, accent and microphone. Splitting
> by turn leaks the speaker across train and test and **inflates every metric**, invisibly.

### 5.2d — Dataset revisions

Every build produces a content hash over `(turn_ids, label_ids, split assignment)`, written to
`dataset_revisions`. **Every training run and every eval run records that hash.** A metric you
cannot attribute to a dataset version is not reproducible.

### Acceptance criteria

- [ ] ≥ 1,000 turns assembled with source tags
- [ ] Consent-revoked turns excluded, and the exclusion recorded
- [ ] Synthetic ≤ 35% of train, **0% of eval**
- [ ] **Speaker-leakage assertion present and passing**; a deliberately leaked fixture fails it
- [ ] Splits stratified; every split spans the full score range
- [ ] Dataset revision hash reproducible across two identical builds

---

## TASK 5.3 — Annotation interface and protocol (day 19)

### 5.3a — Interface requirements

An internal tool at `/app/annotate` (admin only), or a standalone local app. It must show:

- the question
- the answer text (**PII-scrubbed version only**)
- **the audio**, playable
- the criterion being scored
- **the full anchor descriptors for all five points**
- a five-point input plus a notes field (required for extremes)

**It must NEVER show the model's prediction.** Anchoring an annotator to a model output
contaminates every agreement figure computed afterwards, and the contamination is invisible in
the results.

### 5.3b — Order randomisation

**Randomise across criteria and sessions.** Labelling all "structure" scores consecutively
causes the internal standard to drift; labelling one session's turns consecutively causes each
score to anchor on the previous one.

### 5.3c — The double-labelled subset ⚠️ REQUIRED

- **200 turns** labelled independently by **at least two annotators** (`round = 1` and
  `round = 2`, different `annotator_id`).
- Compute **inter-annotator agreement (QWK) per criterion and overall.**
- **This is the ceiling for every model metric that follows.** Publish it beside every model
  number.
- **Compute it first.** If humans agree at < 0.5 on a criterion, **fix the rubric anchors before
  training anything.** A model cannot be more consistent than its labels.
- Disagreements greater than one point go to an adjudication round (`round = 3`), resolved by
  discussion, with the adjudicated label used as ground truth.

### 5.3d — Model pre-labelling (training split ONLY)

Permitted, to speed up labelling — **with rules**:

- **Training split only. Never the evaluation split.**
- Human reviews and corrects every pre-label; the interface must not default to accept.
- **The correction rate is recorded and disclosed** in the README.
- Pre-labelled-then-corrected turns are tagged so their effect can be ablated.

> **The evaluation set is labelled by humans only and is never shown to any generating model.**
> If the eval set were model-labelled, you would be measuring how well a small model imitates a
> big one — distillation, not human agreement — and "my fine-tune beats the frontier baseline"
> becomes incoherent, because the baseline is the ground truth and scores 1.0 by construction.

### Acceptance criteria

- [ ] 5,000–7,000 labels collected
- [ ] Interface never displays a model prediction (verified by inspection **and** a test)
- [ ] Annotation order is randomised
- [ ] 200-turn double-labelled subset complete with two independent annotators
- [ ] **IAA computed and published per criterion**
- [ ] Adjudication round completed for disagreements > 1 point
- [ ] Correction rate on pre-labelled turns recorded
- [ ] A test asserts zero evaluation-split turns were ever model-pre-labelled

---

## TASK 5.4 — Training (day 20)

**Run the baselines first.** They are fast, they establish the floor, and if the fine-tune is
delayed you still have a results table.

### 5.4a — Baselines (rows 1–4)

| Row | Configuration |
|---|---|
| 1 | Majority-class per criterion |
| 2 | **Deterministic features only** (word count, duration, wpm, filler rate, pause stats) + ridge regression |
| 3 | Frontier zero-shot with the rubric in the prompt |
| 4 | **Frontier few-shot with anchor examples — the real baseline to beat** |

Row 2 is often startlingly competitive on concision. **Report it.** Publishing a baseline that
nearly matches your model makes every other claim more believable, not less.

### 5.4b — The fine-tune (rows 5–7)

`services/training/train.py`, runnable on Kaggle/Colab and locally.

```python
Base model      microsoft/deberta-v3-base
Input           f"{question} [SEP] {answer}"  → 512 tokens, truncated from the answer start
Heads           one lightweight regression head per criterion, shared encoder (multi-task)
Aux features    answer duration, word count, concatenated before the heads
Output          sigmoid → mapped to the rubric scale
Loss            MSE on the normalised scale + auxiliary soft ordinal term
Batch           16, grad accumulation → 32 effective
LR              2e-5, linear warmup over the first 10% of steps, cosine decay
Epochs          4, early stopping on VALIDATION KAPPA, patience 1
Precision       bf16 where supported, else fp16
Regularisation  dropout 0.1, weight decay 0.01
Augmentation    filler injection + mild paraphrase — TRAINING SPLIT ONLY
Seeds           3 per configuration, ALWAYS
```

**Requirements:**
- Early stopping is on **validation kappa**, not training loss. Small datasets overfit fast.
- Augmentation applied to the training split **only**. Augmenting validation or test invalidates
  the metric.
- **Three seeds per configuration**, checkpoints all kept.
- Every run logged to **W&B with the dataset revision hash**.
- **Assert at startup that no test-split turn appears in the training data.** Fail loudly.

### 5.4c — Ensemble and calibration (row 7 — the shipped configuration)

- Average the three seeds at inference.
- **Their standard deviation becomes the confidence value shown in the product.** This is the
  same number that drives the "not enough signal" gate — a nearly free and well-behaved
  uncertainty estimate.
- **Isotonic regression per criterion, fitted on the validation split**, mapping raw output onto
  the rubric scale.
- **Fitted on validation, evaluated on test, never fitted on test.**
- Report expected calibration error **before and after**.

### 5.4d — LoRA ablation (row 8)

LoRA adapter on a 1.5B instruct model. **For the comparison and for the discussion of why it
was not shipped** — slower, larger, harder to calibrate, and the rationale is exactly the part
that does not need training. One run is enough; this is a row, not a project.

### 5.4e — Attribution spans

Token-level attribution over each criterion head produces evidence spans naturally. Map token
spans back to character offsets in the answer text, and **verify by exact substring match**
exactly as in Phase 2. The verification rule does not relax because the spans now come from a
model you trained.

### Acceptance criteria

- [ ] All 8 ablation rows run, three seeds where applicable
- [ ] Training completes in < 30 min on a free T4
- [ ] Early stopping fires on validation kappa
- [ ] **Train/test leakage assertion present and passing**
- [ ] Calibration fitted on validation only (a test asserts test data is never touched)
- [ ] ECE reported before and after
- [ ] Every run in W&B with a dataset revision hash
- [ ] Confidence derives from seed disagreement and correlates with error on held-out data
- [ ] Attribution spans verify by exact substring match

---

## TASK 5.5 — Evaluation harness and deployment (day 21)

### 5.5a — `make eval`

One command computes all Level-3 metrics against the held-out set and writes an `eval_runs` row.

| Metric | Definition |
|---|---|
| **QWK** | Per criterion and overall. **Always reported beside the human ceiling.** |
| MAE | In rubric points — interpretable, what a user would feel |
| Spearman | Ranking preservation — what progress tracking actually depends on |
| Adjacent accuracy | Fraction within one point — the practical usefulness threshold |
| ECE | Whether stated confidence means anything |
| **Score stability** | Std dev across repeated runs on identical input. Should be **zero** for the encoder — report it anyway, because it is the number that justifies not shipping a prompted model. |
| **Evidence validity** | Fraction of spans found verbatim. **Must be 100% by construction; measured to prove it.** |
| **Fairness deltas** | Score differences across speaking rate, accent group and vocabulary richness, **controlling for human-labelled content quality**. A material gap is a **defect**, not a curiosity. |
| Cost & latency | Per session — the economic argument for the fine-tune |

### 5.5b — Methodology discipline (enforced in code)

- **Three seeds, report mean and spread.** A single run is an anecdote.
- **Hold out a third of the human labels and touch it only when publishing a number.** The
  harness must refuse to evaluate on the reporting split unless explicitly flagged
  `--publish`, and it logs every such access.
- Every figure carries its **dataset revision, model version and date**. Numbers without
  provenance are marketing.
- **Publish the failures too.** The harness emits a "weakest criteria" section and a set of
  worked failure cases. A README showing where the scorer is weakest is far more convincing
  than one showing only the headline.

### 5.5c — Model registry and promotion

- Register the artefact with metrics, dataset revision and status.
- **Promotion to `active` requires beating the current active version on held-out kappa across
  all three seeds** — not on one lucky run.
- **Rollback is a status change, not a redeploy.**
- The realtime and coach services read the active version from the registry at startup and on a
  pub/sub signal.

### 5.5d — Shadow mode (CS-12)

The prompted baseline runs alongside the fine-tune on a **sampled fraction (10%) of live
turns**, writing to `turn_scores` with its own `model_version`. This keeps the comparison claim
true **after** deployment rather than only at training time — a live measurement, not a
historical one.

### 5.5e — The results table

Generated automatically into `docs/RESULTS.md` and the README:

```
| Configuration                      | QWK   | MAE  | Spearman | Adj. acc | ECE   | Cost/session | Latency |
|------------------------------------|-------|------|----------|----------|-------|--------------|---------|
| Human ceiling (2 annotators)       | 0.78  | —    | —        | —        | —     | —            | —       |
| Majority class                     | 0.00  | ...  |          |          |       |              |         |
| Deterministic features + ridge     | ...   |      |          |          |       |              |         |
| Frontier zero-shot                 | ...   |      |          |          |       |              |         |
| Frontier few-shot (baseline)       | 0.52  |      |          |          |       |              |         |
| Fine-tuned encoder, 1 seed         | ...   |      |          |          |       |              |         |
| Fine-tuned encoder, 3-seed ens.    | ...   |      |          |          |       |              |         |
| + isotonic calibration  ← SHIPPED  | 0.71  |      |          |          |       |              |         |
| LoRA 1.5B (not shipped)            | ...   |      |          |          |       |              |         |
```

Every row carries mean ± std across seeds. **The human ceiling is the first row**, always.

### Acceptance criteria

- [ ] `make eval` produces all metrics and writes an `eval_runs` row
- [ ] Reporting split is protected behind `--publish` and every access is logged
- [ ] Fairness deltas computed across speaking rate, accent and vocabulary richness
- [ ] Evidence validity is 100% and measured
- [ ] Score stability is zero for the encoder, reported anyway
- [ ] Promotion requires beating the active version on all three seeds
- [ ] Rollback is a status change with no redeploy (tested)
- [ ] Shadow mode writing baseline scores on 10% of live turns
- [ ] `docs/RESULTS.md` generated with the human ceiling as the first row
- [ ] A failure-cases section exists with worked examples

---

## TASK 5.6 — The honest fallback

**If the fine-tune does not beat the prompted baseline:** this is a legitimate outcome and
still a strong result if measured properly. Report it honestly, analyse why (usually dataset
size or rubric ambiguity), and write the analysis into `docs/RESULTS.md`. The story becomes
*"I ran the experiment and I can tell you when fine-tuning is not worth it"* — which many
engineers cannot say.

**If Phase 5 becomes genuinely impossible in the time remaining:**
1. Ship the prompted scorer, **labelled in the UI and README as the baseline**.
2. **Publish the human-labelled evaluation set and its inter-annotator agreement figure.**
3. State in the README that the fine-tune is the next milestone, **with the dataset already
   collected.**

> Never claim a fine-tune you did not run. Never write a metric that was not measured. A
> fabricated number is the one thing in this project that would actually damage the author's
> prospects, and any code you write must never emit a placeholder metric that could survive
> into a README.

---

## Phase 5 definition of done

- [ ] `model_versions`, `eval_runs`, `dataset_revisions` migrated
- [ ] ≥ 1,000 turns, ≥ 8 speakers, PII-scrubbed, consent-filtered
- [ ] Splits by session and speaker, with a passing leakage assertion
- [ ] 5,000–7,000 human labels; evaluation split human-only
- [ ] **200-turn double-labelled subset; IAA published per criterion**
- [ ] All 8 ablation rows, three seeds
- [ ] Isotonic calibration on validation; ECE before/after
- [ ] Scorer promoted to `active` via the registry
- [ ] Shadow mode running
- [ ] `docs/RESULTS.md` with the human ceiling first and failure cases included
