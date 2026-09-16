# 0026 — `coach` and `realtime` image size targets not met

**Measured** (`docker images`, 2026-09-17): api 351 MB (target < 400, met), coach 776 MB (target
< 400), realtime 1.08 GB (target < 800, no weights inside).

**Already done:** multi-stage builds, runtime copies only the venv, no bytecode precompilation,
vendored `tests/` directories stripped, no model weights in any layer.

**What is left, and why it was not taken now:**
- `litellm` (~120 MB in both) could become a thin HTTP client for the two providers actually used
  (Groq, Ollama). That touches every model call site, including the persona hot path, which makes
  it more than a packaging change.
- `coach`: spaCy + `en_core_web_sm` power deterministic delivery metrics. Replacing them changes
  metric definitions that reports depend on.
- `realtime`: ctranslate2 (faster-whisper) and PyAV are the ASR path. The alternative is a smaller
  ASR runtime, which is a latency and WER decision, not a packaging one.

The targets are recorded as missed rather than quietly relaxed.
