# 0028 — Enforcing the difficulty ladder in code, and blocking praise

Date: 2026-09-27
Status: implemented

## What Level 2 actually found

The Phase 6 Level 2 persona-adherence run (eval_runs `01a0aca9`, 2026-09-16, local
`qwen2.5:3b-instruct`) failed on two of its own criteria, and the Phase 6 specification calls both
of them defects rather than warnings:

1. **Character break rate 0.05** (3 of 60). All three were *praise* — "Sure, that's impressive. Can
   you tell me more about…". The post-generation check (`persona/safety.py`) matched rubric leaks,
   coaching phrases and grading language, and matched none of them, because praise contains no
   coaching and no grade. The spec's target is zero and says any non-zero result fails the suite.
2. **Difficulty separation on interruptions p = 0.885**, with an interruption rate of **0.0 on
   every tier including hard**, measured against a deliberate >120-word ramble. The spec's words:
   "If gentle and hard are statistically indistinguishable, fail the suite — the ladder is
   decorative and that is a defect."

The second was the more serious of the two. `interrupt_over_words: 120` existed on the hard tier of
every scenario and was rendered into the semi-static layer as an instruction, and nothing in
`services/realtime` enforced it. The other two hard-tier parameters were already enforced in code —
`silence_after_answer_ms` with a real `asyncio.sleep` in `turn.py`, `followups_on_vague` through
`advance_plan`'s `followups_cap` — so this one was the outlier, not the pattern.

## Decisions

### Praise is a separate rule, matched as phrases, never as bare adjectives

`PRAISE_BLOCKLIST` is its own list reported under its own violation reason (`praise:…`), not extra
entries in `COACHING_BLOCKLIST`, because the Level 2 report distinguishes praise from coaching and
grading and a log line that conflates them makes the next regression look like the previous one.

Every entry is a multi-word phrase. Bare adjectives are excluded deliberately: the persona has
legitimate reasons to say "impressive" ("what's the most impressive system you've built?"),
"perfect" ("in a perfect world…") and "strong" ("what made it a strong candidate for caching?")
inside an ordinary question. A false positive is not free — it spends a regeneration on the latency
path and, if the regeneration also trips, produces a canned deflection, which the same Level 2 run
already flagged as reading like the interviewer had not listened. The test file asserts the
non-matches as carefully as the matches, and it caught exactly this: "strong candidate" was in the
first draft of the list and had to be narrowed to "you're a strong candidate".

Neutral acknowledgements must keep passing. The judge prompt rules them not-breaks explicitly, and
the difficulty ladder depends on acknowledgements existing at all (`ack_length` is one of the three
behavioural measures). Nothing in the list matches "Okay.", "Right.", "Got it.", "I see.", "Mm." or
"Thanks.".

The static prompt layer also now forbids praise in concrete terms with examples, and is bumped to
**v1.2.0** (CLAUDE.md §11: never edit a prompt without bumping its version). The blocklist is the
net, not the plan — the prompt is where the behaviour is supposed to come from.

### The ramble interrupt forces an endpoint; it is not barge-in

`exceeds_ramble_word_cap` is a pure function in the endpointing cascade, and `frame_pipeline`
checks it in the `listening` branch against the running partial transcript. When it fires, the turn
starts immediately instead of waiting for silence.

- It routes through `endpointing`, because `listening -> thinking` is not a legal transition. The
  WebSocket protocol and the state-machine transition table are both untouched — no new message
  type, no new state, no new edge. Only *who decides the turn is over* changes.
- This is **not** the full-duplex barge-in that CLAUDE.md §9 puts out of scope. We stop listening,
  then speak, exactly as on an ordinary endpoint. There is no moment where both parties are live.
- `cap is None` on gentle and standard means never interrupt. That is the point: if the cap applied
  everywhere the tiers would collapse into one, which is the defect inverted rather than fixed.
- The count is on the *partial* transcript, so it lags the audio by up to one partial interval. The
  prompt text says "roughly 120 words" too. An interruption a few words late is still an
  interruption.
- `utterance.interrupted_ramble` reaches the persona's dynamic layer, which tells it plainly that it
  is cutting the candidate off mid-sentence. Without that the reply answers a fragment as though it
  were a finished answer, which reads as a bug rather than as pressure.

### Stop-on-speech is suppressed for that one reply

Found while wiring it up, and the reason `SessionRuntime.ramble_interrupt_active` exists. The
candidate is by definition still mid-sentence when we cut them off, so their trailing speech would
satisfy the ordinary stop-on-speech guard (Task 1.5d) and cancel the interruption the instant it
began. The hard tier's one real escalation would then be enforced, measurable as enforced, and
still never heard. The flag suppresses barge-in until the candidate starts a fresh utterance, and
holds the guard at zero so a genuine later barge-in starts from scratch.

### The Level 2 eval now exercises the enforced path

`scripts/eval_persona.py` applies the same cap: on the hard tier it truncates a fixture answer at
`interrupt_over_words` and sets `interrupted_ramble`, because that is what the realtime service does
to the audio. Left as it was, the eval fed the whole ramble to the model and waited to see whether
the model volunteered an interruption — measuring something no user can ever experience, and
reporting 0.0 no matter how well the feature works.

## Latency

CLAUDE.md §1 requires saying so explicitly. Both changes touch the turn path:

- The praise check is substring matching over one reply on a list of ~60 phrases — microseconds,
  and it runs where the coaching check already ran. What is *not* free is a violation: a blocked
  reply costs one regeneration. The narrow phrase list and the false-positive tests exist to keep
  that rare, but on a model that praises often this will raise p95. That is the intended trade:
  CLAUDE.md §1.4 and the Phase 6 target treat a character break as a correctness failure, not a
  latency one.
- The ramble interrupt **reduces** latency for the turn it fires on — the turn starts while the
  candidate is still speaking instead of after silence plus the endpointing window. The word count
  is a `str.split()` on the partial transcript per 20 ms window on the hard tier only.

Neither adds a blocking call, a model call, a DB write or an unbounded await.

## Not resolved here

The measured Level 2 numbers in `README.md` and `docs/PROGRESS.md` still describe the 2026-09-16
run, because that is the last run that happened. Re-running Level 2 against a live persona model is
what would show a break rate of zero and a separated interruption measure, and until it is run the
published figures stay as they are. Writing the improved numbers before measuring them is exactly
what CLAUDE.md §1.10 forbids.
