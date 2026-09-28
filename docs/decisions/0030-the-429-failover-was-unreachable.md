# 0030 — The persona's "429 → local model" failover existed but was unreachable

## Context

Groq's daily token quota on this project's key ran out mid-testing:

```
Rate limit reached for model `openai/gpt-oss-20b` ... on tokens per day (TPD):
Limit 200000, Used 199459, Requested 1430. Please try again in 6m24.048s
```

That is an account limit, not a defect. What the account limit exposed is a defect.

Every session against the exhausted key behaved like this, on every turn:

```
  ♪ [persona] "Let's keep going — what's your answer?"     <- the OPENING line
  › you: "I disagreed with my manager about the deadline, so I brought data..."
  ♪ [persona] "Let's stay focused on the conversation — go ahead and answer the question."
```

Both are entries from `safety.py::CANNED_DEFLECTIONS`. The persona never once addressed what the
candidate said. The opener — the first thing a candidate hears, before they have said anything at
all — told them to answer a question nobody had asked.

## Investigation

Task 2.1's degraded table already specifies the right behaviour: *"persona model 429 / error →
switch to MODEL_PERSONA_LOCAL for the remainder of the session"*. `SessionRuntime` has the flag
(`persona_use_local_for_remainder`), `turn.py` and `opening.py` both read it to pick the model,
and `MODEL_PERSONA_LOCAL` was configured. The mechanism was fully built.

Nothing set the flag except `timeouts.py::_handle_thinking_timeout`, which fires when the persona
model is too **slow** — the 5s `thinking` timeout. A 429 is the opposite of slow: it returns in
under 100ms. So the timeout never fired, the flag was never set, and the failover was dead code
for the one failure mode its own table entry names first.

Two further consequences followed from `generate_persona_reply` never raising (by design — it
always returns something speakable):

- `MAX_GENERATION_ATTEMPTS = 2` exists so a reply that breaks character can be regenerated once.
  On a 429 both attempts were spent ~80ms apart on the same dead provider, then the canned
  deflection.
- `opening.py`'s `except Exception` branch, whose job is to fall back to the scenario's authored
  `opening_strategy` text, was unreachable for a provider failure. That is why the opener was a
  deflection rather than the scenario's own line — a *worse* outcome than the fallback that was
  already written and sitting right there.

## Decision

`PersonaReplyResult.failed_on_provider_error` distinguishes "every attempt raised" from "the model
answered and kept breaking character". The two need opposite responses: a different provider fixes
the first and does nothing for the second. The existing `generation_error:*` vs `empty_reply`
violation split (added 2026-09-27) already carried the information; nothing consumed it.

- `turn.py`: on a provider failure, log `persona_provider_failover`, set
  `persona_use_local_for_remainder`, send `degraded` (component="persona"), and regenerate on
  `MODEL_PERSONA_LOCAL` — so the *current* turn gets a real reply, not just later ones.
- `opening.py`: the same, and if the failover also fails, prefer the scenario's
  `opening_strategy` over a canned deflection.

A mixed outcome — one attempt broke character, the next hit a provider error — is deliberately
*not* a provider failure. The provider demonstrably worked, and abandoning the hosted model for
the rest of the session on one transient blip is the wrong trade.

## Consequence

Verified end to end against the exhausted key, with `MODEL_PERSONA_LOCAL`
(`ollama/qwen2.5:3b-instruct`) running locally:

```
  › you: "I disagreed with my manager about the deadline, so I brought data to the
          meeting and we agreed on a smaller scope."
  ♪ [persona] "Okay. What was the tool or process you used to bring data to the meeting?"
```

A real, in-character, contextual follow-up, on a key with no quota left.

The cost is latency: the local 3B model's TTFT was 1760ms against the hosted model's ~570ms, and
the failover turn pays for the failed hosted attempts on top. Both are far outside the 1400ms
budget. That is the correct trade for a *degraded* path — CLAUDE.md §6 is "degrades before it
dies" — but it means a quota-exhausted session is a slow session, not merely a quieter one, and
the `degraded` signal now says so explicitly instead of hiding it behind a canned line.

`MODEL_PERSONA_LOCAL` must actually be pulled for any of this to work. It was configured as
`qwen2.5:3b-instruct` and not present in the local Ollama; the failover found nothing and the
session got the deflection anyway. A configured fallback that was never once exercised is not a
fallback. Worth a startup check.
