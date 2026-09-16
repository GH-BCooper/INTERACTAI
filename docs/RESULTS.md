# Results (Task 5.5e)

Generated: 2026-08-24T12:51:09.681309+00:00
Dataset revision: `none`

**No real human inter-annotator agreement figure exists in this environment yet.** docs/PHASE5-WALKTHROUGH.md explains why (no recruited-session data, no second independent human annotator) and what to do about it. Every number below is reported honestly against whatever data currently exists, which is NOT the target Phase 5 dataset — none of it should be read as a real Phase 5 result.

| Configuration | QWK | MAE | Spearman | Adj. acc | ECE | Cost/session | Latency |
|---|---|---|---|---|---|---|---|
| Human ceiling (2 annotators) | TODO: measure | - | - | - | - | - | - |
| Majority class | TODO: measure | | | | | | |
| Deterministic features + ridge | TODO: measure | | | | | | |
| Frontier zero-shot | TODO: measure | | | | | | |
| Frontier few-shot (baseline) | TODO: measure | | | | | | |
| Fine-tuned encoder, 1 seed | TODO: measure | | | | | | |
| Fine-tuned encoder, 3-seed ens. | TODO: measure | | | | | | |
| + isotonic calibration <- SHIPPED | TODO: measure | | | | | | |
| LoRA 1.5B (not shipped) | TODO: measure | | | | | | |

## Weakest criteria and failure cases

No per-criterion breakdown exists yet - no eval_runs row has been published against real labelled data.

## Honest fallback (Task 5.6)

If the numbers above are placeholders or come from smoke-test data: the prompted scorer (`services/coach/app/scorer/prompted.py`) is what ships today, labelled explicitly as the baseline. `docs/PHASE5-WALKTHROUGH.md` is the concrete next-steps document for collecting real data and training a real fine-tune on top of the infrastructure built this phase.
