# Prompts

Empty in Phase 0 on purpose. Persona/narrator/planner prompts are built in Phase 1+
(docs/phase-1-BUILD.md, docs/phase-2-BUILD.md) — this directory exists now so the layout
matches CLAUDE.md from day one.

Per CLAUDE.md §11: prompts are versioned artefacts here, never string literals in application
code. Every prompt file carries a semantic version in its front matter, and every `model_calls`
row records the version that produced it. Never edit a prompt without bumping its version.
