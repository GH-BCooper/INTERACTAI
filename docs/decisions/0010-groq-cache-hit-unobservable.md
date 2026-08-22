# 0010 — Groq exposes no cache-hit signal; `model_calls.cached` cannot be measured as specified

Task 2.3's acceptance criteria include: "Prefix caching verified: `model_calls.cached` is true
for ≥ 80% of turns after the first." Tested directly against the real, configured
`MODEL_PERSONA` (`groq/openai/gpt-oss-20b`, via LiteLLM) with a long, byte-identical system
prefix repeated across three consecutive calls: every response's
`usage.prompt_tokens_details` is `None`, and `_hidden_params` carries no `cache_hit` field or
equivalent — unlike Anthropic's `cache_read_input_tokens`/`cache_creation_input_tokens` or
OpenAI's `prompt_tokens_details.cached_tokens`, Groq's chat completions API does not return
whether a request's prefix was served from cache, whether or not caching happened server-side.

`prompt_time` (Groq's own server-side timing field) also showed no clear, attributable
before/after signal across the three calls in that test — nowhere near reliable enough to
reverse-engineer a cache-hit boolean from timing alone.

## What this implementation does

`services/realtime/app/persona/engine.py` writes `model_calls.cached = False` for every
persona call. This is honest given what's measurable, not a claim that caching isn't
happening — it likely is, server-side, invisibly. CLAUDE.md §10 ("never fabricate a metric...
never a plausible placeholder") rules out inferring a heuristic `True` from timing and
presenting it as measured fact.

The engineering response to Task 2.3a's actual intent — "assembly order is load-bearing... a
provider with automatic prefix caching can hit its cache" — still stands and is implemented in
full: static and brief layers are separate, byte-identical-per-session `system` messages,
assembled in the mandated order, with nothing variable placed above them. That is the
correctness property this codebase controls. Whether Groq's servers actually exploit it is not
something this API surface will confirm either way.

If a future model role moves to a provider that does expose this (Anthropic, or OpenAI directly
rather than via Groq), `cached` should be wired to that provider's real field at that point —
this decision is provider-specific, not a permanent stance.
