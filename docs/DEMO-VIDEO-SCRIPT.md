# Demo video script (TASK 6.8): for a human to record

This cannot be produced by an agent honestly: beat 2 must be live, uncut, real audio of a person
speaking. Everything needed to record it is below. Target under 3:15. If 30 seconds must go, cut
beat 3, never beat 6.

**Before recording:** `make up && make migrate && make seed`, run `api`, `realtime`, `coach`, `web`;
sign in; have `/app/observability` and `/app/evals` open in other tabs; run `make eval-speech` and
`uv run python scripts/publish_metrics.py` so the numbers on screen are today's.

| Beat | Time | On screen | Say |
|---|---|---|---|
| 1. Setup | 15 s | Scenario library → *Behavioural / STAR screen: standard* card | "This is InteractAI. I'm going to practise a behavioural interview out loud." Nothing about architecture yet. |
| 2. Conversation | 60 s | Practice room. **Do not cut.** | Answer the first question deliberately vaguely ("we disagreed, it worked out"). Let the follow-up land; answer it properly with a number. |
| 3. Pressure | 20 s | Restart on the **hard** tier; ramble for 30+ seconds | Nothing; let the persona cut in or go silent. |
| 4. Report | 40 s | Report page; select *Specificity*; click one evidence span | **Say nothing.** Let the audio play the exact moment. |
| 5. Architecture | 20 s | Landing page diagram | "The interviewer is on the latency path and must answer fast. The coach is off it, queued, so scoring can take as long as it needs." |
| 6. Close | 25 s | `/app/observability` latency header with the target line, then `/app/evals` regression chart | State the p50/p95 from the header, **and that the p95 target is 1400 ms and whether it is met on this host**. State scorer QWK beside the human ceiling, or say plainly that no human-labelled split exists yet. |

After recording: upload, then replace the "Demo video" line at the top of `README.md` and add the
link to the landing page hero.
