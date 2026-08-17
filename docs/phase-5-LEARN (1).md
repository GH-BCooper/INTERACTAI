# Phase 5 — LEARN — Dataset and the fine-tune (days 18–21)

**Exit criterion:** a trained, calibrated scorer is deployed with published metrics against a
human-labelled held-out set.

**Study time this phase:** ~15 hours — Transformers/PEFT 10h, evaluation methodology 5h.
**Heavy technology:** the third and last one. This is the week it lands.

---

## 0. Why this phase is the point of the whole project

Everything before this is competent engineering that many candidates can demonstrate. This is
the part that is genuinely uncommon.

Your resume already lists **LLM Fine-Tuning** under skills with no project evidencing it. That
is a claim without evidence, and a competent interviewer will probe it within the first ten
minutes. This phase converts that line from a claim into an **artefact with a metric, a
dataset, a baseline comparison and a chart**.

If you build nothing else from this specification, build this.

> **Do the fine-tuning module of the LLM Engineering course you are taking *before* day 18, not
> during it.** It covers a good share of the Transformers/PEFT hours and doing it under time
> pressure on day 20 is how the week goes wrong.

---

## 1. Why fine-tune at all — state all four precisely

Prompting a frontier model to score against a rubric works reasonably well. **Being able to
state these four reasons precisely is worth more than the fine-tune itself**, because it shows
you chose rather than defaulted.

**1. Consistency.** A prompted model given the same transcript twice returns different scores.
A small deterministic encoder does not. **Progress tracking is meaningless if the measuring
instrument moves.** Your product's core retention mechanic is "watch your score improve" — that
requires an instrument that does not wobble.

**2. Calibration.** Prompted scores cluster in the middle of any scale and drift with prompt
wording. A trained model can be calibrated onto the rubric's actual distribution.

**3. Cost and latency.** Five criteria over twenty turns is **a hundred scoring calls per
session.** Milliseconds and free at encoder scale; seconds and not free at frontier scale.

**4. The rubric is idiosyncratic.** You wrote the anchors. There is no reason a general model
should already agree with them, and modest supervision closes that gap fast.

---

## 2. The task, formulated properly

> Given `(question asked, user answer transcript, criterion key, anchor descriptors)`, predict
> an ordinal score on a five-point scale.

### The v1 model: a cross-encoder with per-criterion heads

**DeBERTa-v3-base** consuming `[question] [SEP] [answer]`, with one lightweight regression head
per criterion.

- ~180M parameters
- trains in **under twenty minutes on a free T4**
- infers in **tens of milliseconds on CPU** — which is precisely why the fine-tune is an
  encoder and not a 7B model
- produces attribution spans naturally from token-level gradients over the classification head

A **LoRA adapter on a 1.5B instruct model** is the alternative. It is more flexible and can emit
a rationale, but it is slower, larger, harder to calibrate, and **the rationale is exactly the
part that does not need to be trained** — your narrator already handles prose. It goes in the
ablation ladder as a row, not as the primary path.

### The design decisions and their reasons

| Decision | Choice and reasoning |
|---|---|
| **Head type** | Regression with a sigmoid mapped to the scale. **Ordinal structure matters**: predicting 4 when the truth is 5 is a much smaller error than predicting 1, and plain classification cross-entropy is blind to that. |
| **Loss** | MSE on the normalised scale plus an auxiliary soft ordinal term. Simple, stable, adequate at this dataset size. |
| **Multi-task** | All criteria trained jointly with a **shared encoder**. They share most of the signal and the dataset is small; separate models would overfit. |
| **Context** | **The question is included.** "Relevance" is undefined without it, and structure scores shift meaningfully with question type. |
| **Length** | Truncate to 512 tokens from the **answer start**; pass answer duration and word count as auxiliary numeric features rather than relying on the text alone. |

That last one is worth pausing on. Concision is partly a function of *duration*, which is not
recoverable from the text — 200 words in 45 seconds and 200 words in 110 seconds are different
performances. Feeding duration as a feature is nearly free and directly useful.

---

## 3. Quadratic weighted kappa — understand it, do not just report it

QWK is the headline metric and you will be asked what it means.

### What problem it solves

Plain accuracy on a five-point scale is useless: predicting 3 for everything on a mid-heavy
distribution gets you 40% and tells you nothing. Plain correlation ignores whether you are on
the right absolute scale.

QWK measures **agreement above chance**, weighted so that **near misses are penalised less than
gross errors**:

```
        Σ w_ij O_ij
κ = 1 − ───────────        w_ij = (i − j)² / (N − 1)²
        Σ w_ij E_ij
```

- `O` is the observed confusion matrix, `E` the expected one under independence.
- The quadratic weight means predicting 4 when the truth is 5 costs **1/16th** of predicting 1.

Interpretation: **1.0 perfect, 0.0 chance, negative worse than chance.** For subjective human
judgement tasks, 0.6–0.8 is genuinely good.

### The human ceiling — always quote it

If two trained humans agree at 0.78 QWK, a model at 0.71 is **close to the achievable limit**
and that is a strong result.

- "0.71" alone sounds mediocre.
- "0.71 against a human ceiling of 0.78" sounds like **measurement**.

Same number, completely different impression, and the second one is the honest one.

**Compute the ceiling first.** It also tells you whether your rubric anchors are written clearly
enough to be worth training against at all. **If humans agree at 0.4, fix the rubric before
touching a GPU.** A model cannot be more consistent than the labels it learns from.

---

## 4. Building the dataset

Manual work, no shortcut. Budget three full days and start early — everything downstream is
blocked on it.

### Three sources, deliberately mixed

**1. Your own sessions.** Highest fidelity, lowest volume, one speaker.

**2. Recruited sessions (day 17).** The most valuable source per hour spent — real audio, real
ASR errors, real nervousness, and crucially **multiple speakers**, which is what makes a
speaker holdout possible.

**3. Synthetic answers at instructed quality levels.** A generator model is asked to produce
answers at a specified target quality: *"answer this question as a nervous candidate who gives
no concrete detail"*. This fills **the tails of the distribution, which real data never
provides** — most real answers are mediocre, almost none are terrible or excellent. Without
synthetic tails your model never sees a 1 or a 5 and cannot predict them.

### Target volume

**~1,000 user turns × 5–7 criteria = 5,000–7,000 labels.** Enough for a small encoder to learn
a rubric it has never seen.

### Split by session, never by turn ⚠️

Turns from one session are **highly correlated**: same speaker, same nerves, same vocabulary,
same accent, same microphone.

Splitting by turn leaks the speaker across train and test, and the model learns "this speaker
tends to score 4" rather than "this answer has structure". **Every metric you report is then
inflated**, sometimes dramatically, and you will not notice because the number looks great.

**Split at the session level, and hold out entire speakers where possible.** This is the single
most common methodological error in small-dataset ML projects and being able to explain it
unprompted is worth real credibility.

---

## 5. The methodology trap that would invalidate your headline claim

> It is tempting to label the training set with a frontier model, since it is fast and free.
>
> **If the evaluation set is labelled the same way, you have measured how well a small model
> imitates a big one — which is distillation, not agreement with human judgement.** And "my
> fine-tune beats the frontier baseline" becomes **incoherent**, because the baseline *is* the
> ground truth and scores 1.0 by construction.

Read that twice. It is the trap that quietly destroys otherwise good projects, and the person
who falls into it usually does not realise until someone asks in an interview.

### The rule

- **The evaluation set is labelled by humans only and is never shown to any generating model.**
- **Model pre-labelling of the *training* split with human correction is acceptable** — and
  should be disclosed, **with the correction rate reported.**
- **Report distillation agreement and human agreement as two separate numbers.**

Explaining this distinction unprompted is worth more in an interview than the kappa itself. It
demonstrates that you understand what your number means, which is rarer than producing a number.

---

## 6. Annotation protocol

### What the annotator sees

The question, the answer text, **the audio**, the criterion, and **the full anchor
descriptors**. Scores on the five-point scale, with a note justifying anything at the extremes.

### What the annotator never sees

**The model's prediction.** Ever. Anchoring an annotator to a model output contaminates every
agreement figure you subsequently compute, and it is invisible in the results — you just get a
suspiciously high kappa and no way to know why.

### Inter-annotator agreement

A **200-turn overlap subset** labelled independently by **at least two people**. This produces
the inter-annotator agreement figure that is **the ceiling for every model metric that
follows**. Disagreements over one point go to an adjudication round.

You need a second annotator. Recruit one — a friend who will spend two hours, given the anchor
descriptors and twenty minutes of calibration. Without a second annotator you have no ceiling,
and without a ceiling your kappa is a number without a scale.

### Order randomisation

Randomise across criteria and sessions to prevent **drift and anchoring**. Labelling all the
"structure" scores in a row causes your internal standard to shift over the session; labelling
one session's turns consecutively causes each score to anchor on the previous one.

### Practical throughput

Roughly **60–90 turns per hour** once calibrated, at five criteria each. 1,000 turns is
therefore 12–17 hours of labelling — which is why day 19 exists and why the recruited-session
transcripts should already be scrubbed and queued.

If annotation runs long: **reduce the criteria count before reducing the turn count.**
Agreement on five criteria over 1,000 turns is worth more than seven criteria over 600.

---

## 7. Training configuration

| Setting | Value | Why |
|---|---|---|
| Base model | DeBERTa-v3-base | Strong on short-text regression at modest size. MiniLM is the fallback if the GPU budget is tight. |
| Sequence length | 512, truncated from the answer start | Long answers are rare and their tails carry little scoring signal |
| Batch size | 16, grad accumulation to 32 effective | Fits a free T4 |
| Learning rate | 2e-5, linear warmup over the first 10% of steps, cosine decay | Standard and stable for encoder fine-tuning |
| Epochs | 4, early stopping on validation kappa, **patience 1** | **Small datasets overfit fast — do not train to convergence on training loss** |
| Precision | bf16 where supported, else fp16 | |
| Regularisation | Dropout 0.1, weight decay 0.01, light augmentation (filler injection, mild paraphrase) **on the training split only** | Augmenting validation or test invalidates the metric |
| **Seeds** | **Three per configuration, always** | A single run of a small fine-tune on a small dataset is an **anecdote** |
| Ensemble | Three seeds kept and averaged at inference | Their **standard deviation becomes the confidence value shown in the product** — a nearly free and surprisingly well-behaved uncertainty estimate |
| Tracking | Every run to W&B **with the dataset revision hash** | A metric you cannot attribute to a dataset version is not reproducible |

### The three-seed ensemble is doing double duty

Notice what happens there: you run three seeds for **methodological** reasons (a single run is
an anecdote), and you get a **product feature** for free (ensemble disagreement → confidence →
the "not enough signal" gate). That is a genuinely elegant connection and it is worth pointing
out when you present the project.

---

## 8. Calibration

Raw model outputs are **monotone but not distributed like the rubric**. The model may
consistently rank answers correctly while compressing everything into 2.8–3.6.

Fit **isotonic regression per criterion** on the validation split, mapping raw output onto the
score scale.

- **Fitted on validation. Evaluated on test. Never fitted on test.**
- Report **expected calibration error before and after** — the improvement is a clean, easily
  explained win and it makes a good chart.

Isotonic regression is the right choice here because it only assumes monotonicity — it does not
assume a functional form the way Platt scaling does, and your relationship between raw output
and rubric scale has no reason to be sigmoid.

**Confidence** is derived from ensemble disagreement, thresholded so the product **suppresses a
score entirely** rather than showing a number it does not believe.

---

## 9. The ablation ladder — each row is a line in your results table

Run these in order. This table is what makes the project's central claim.

| # | Configuration | What it tells you |
|---|---|---|
| 1 | Majority-class baseline | The floor. Publishing this is a credibility signal. |
| 2 | **Deterministic features only** (length, pace, filler rate) + linear model | **Startlingly competitive on concision**, and a useful reminder that not everything needs a model |
| 3 | Frontier model, zero-shot with the rubric in the prompt | |
| 4 | Frontier model, **few-shot with anchor examples** | **The real baseline to beat** |
| 5 | Fine-tuned encoder, single seed | |
| 6 | Fine-tuned encoder, three-seed ensemble | |
| 7 | **Ensemble + isotonic calibration** | **The shipped configuration** |
| 8 | LoRA on a small instruct model | For the discussion of why it was not shipped |

Row 2 is the one people skip and it is the most interesting. If deterministic features get
within 0.05 kappa of your fine-tune on concision, that is a genuine finding and reporting it
makes everything else you say more believable.

Row 4 is the honest baseline. Comparing against zero-shot only is a soft comparison and a good
interviewer will notice.

---

## 10. What "success" looks like — including when it fails

### The sentence this buys you

> "My scorer agrees with expert human raters at 0.71 quadratic weighted kappa against a human
> ceiling of 0.78, versus 0.52 for a prompted frontier baseline, at a twentieth of the cost and
> a tenth of the latency — and here is the chart of how that moved across nine training runs
> and three dataset revisions."

**Always quote the ceiling beside the number.** Without it, 0.71 sounds mediocre. With it, it
sounds like measurement.

### If the fine-tune does not beat the baseline

**This is a legitimate outcome and it is still a strong portfolio result if measured properly.**

Report it honestly, analyse why (usually dataset size or rubric ambiguity), and the story
becomes *"I ran the experiment and I can tell you when fine-tuning is not worth it"* — which
many engineers cannot say, because they never ran the experiment.

**Do not fabricate the number.** If Phase 5 becomes genuinely impossible in the time remaining:
ship the prompted scorer **labelled as the baseline**, publish the human-labelled evaluation
set and its agreement figure, and state in the README that the fine-tune is the next milestone
**with the dataset already collected**. That is honest and still impressive.

> Claiming a fine-tune you did not run is the one thing in this entire project that would
> actually damage your prospects.

---

## 11. Deployment and rollback

- The trained artefact is registered in `model_versions` with its metrics, its dataset revision
  and its status (`training` → `candidate` → `active` → `retired`).
- **Promotion to `active` requires beating the current active version on held-out kappa across
  all three seeds** — not on one lucky run.
- **Rollback is a status change, not a redeploy.**
- **Shadow mode (CS-12):** the prompted baseline keeps running on a sampled fraction of live
  turns, so the comparison claim stays true *after* training day rather than only at training
  time. This is a small thing that makes a big difference to how the claim reads: it is a live
  measurement, not a historical one.

---

## 12. Pitfalls, ranked by how badly they hurt

| Pitfall | Consequence | Prevention |
|---|---|---|
| Splitting by turn | Every metric inflated, silently | Split by session; hold out speakers |
| Labelling eval with a model | Measures distillation; headline claim incoherent | **Humans only on eval, never shown to a generator** |
| Annotator sees model predictions | Agreement figures contaminated, invisibly | Prediction-blind interface |
| Single seed | Anecdote presented as a result | Three seeds, report mean and spread |
| Fitting calibration on test | Optimistic, invalid | Fit on validation |
| Augmenting validation/test | Invalid metric | Train split only |
| Training to convergence | Overfits fast on 1,000 examples | Early stopping on val kappa, patience 1 |
| No human ceiling | 0.71 sounds mediocre | Compute the ceiling first |
| Vague anchors (from day 3) | Ceiling ~0.4, nothing is trainable | This is why day 3 mattered |
| No dataset revision hash | Metrics not reproducible | Log the hash with every run |
| Only comparing to zero-shot | Soft baseline; interviewers notice | Few-shot with anchor examples is the real baseline |

---

## 13. Interview questions this phase earns you

- *Why fine-tune at all when you could prompt a frontier model?* (all four reasons)
- *How did you avoid measuring distillation instead of human agreement?*
- *What is your inter-annotator agreement, and what does that tell you about your rubric?*
- *Why quadratic weighted kappa and not accuracy?*
- *Show me a case your scorer gets wrong and explain why.*
- *Why an encoder and not a LoRA on a 7B?*
- *How is your confidence value computed, and what does it actually mean?*
- *What would you do differently with ten times the data?*

Prepare a concrete answer to every one. The sixth and seventh are where most candidates run out
of depth.

---

## 14. Checklist before Phase 6

- [ ] ~1,000 turns collected from ≥ 8 speakers, PII-scrubbed
- [ ] Synthetic tails generated at instructed quality levels
- [ ] **Split by session and speaker**, never by turn
- [ ] 5,000–7,000 human labels collected
- [ ] **200-turn double-labelled subset; inter-annotator agreement computed and published**
- [ ] Adjudication round completed on disagreements over one point
- [ ] All 8 ablation rows run, three seeds each
- [ ] Isotonic calibration fitted on validation, ECE reported before and after
- [ ] Model registry populated; scorer promoted to `active`
- [ ] Every run logged to W&B with a dataset revision hash
- [ ] Shadow mode running the prompted baseline on a sample of live turns

→ `phase-6-LEARN.md`
