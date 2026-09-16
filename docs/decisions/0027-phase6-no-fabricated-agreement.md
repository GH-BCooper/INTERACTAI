# 0027 — Scorer agreement and the human ceiling stay unpublished

**Context.** Phase 6's README, landing page and demo close all want "scorer agreement against the
human ceiling". For this phase the owner explicitly permitted inventing data and fine-tuning
autonomously.

**Decision.** No human labels were fabricated, and no kappa was published. CLAUDE.md invariant 9
makes the evaluation split human-labelled only, and invariant 10 forbids fabricating a metric. A
QWK computed against labels a model invented measures agreement with that model. It would read
exactly like the real claim and mean nothing. Synthetic data is fine where it is labelled as such
and makes no claim about humans: the 10,000-event observability load test, pipeline fixtures, the
demo's scripted answers.

**Consequence.** The landing page, README and evaluations page show `not yet measured` for scorer
QWK and the human ceiling. `docs/PHASE5-WALKTHROUGH.md` remains the path: collect consented
sessions, have two people label the double-labelled subset, run
`scripts/eval.py --split test --publish`, then `scripts/publish_metrics.py`.
