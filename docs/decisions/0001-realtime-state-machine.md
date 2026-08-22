# 0001 — Realtime state machine: the 8 server states and 4 client states

`docs/04-state-machine.md` is referenced by CLAUDE.md §14 but does not exist in this repo —
only the phase-0 through phase-6 BUILD/LEARN files and the two setup docs were provided.
`ws-messages.schema.json`'s `state_change` message needs both enums now (Task 0.3), so they
are defined here rather than left as a placeholder.

## Server machine states (8) — `state_change.state`

`connecting → idle → listening → endpointing → thinking → speaking → (idle | degraded | closed)`

| State | Meaning |
|---|---|
| `connecting` | WS upgrade accepted, `hello`/`resume` not yet acknowledged |
| `idle` | Ready, waiting for the user to start speaking |
| `listening` | VAD active, ASR streaming the current utterance |
| `endpointing` | Silence window running; deciding whether the turn has ended |
| `thinking` | ASR finalized; persona model generating a reply |
| `speaking` | TTS streaming to the client |
| `degraded` | First-class recovery state — a component failed, a holding line may be playing (CLAUDE.md §6, AS the anti-dead-air requirement) |
| `closed` | Session ended |

## Client-visible states (4) — `state_change.client_state`

`listening · thinking · speaking · degraded`

The practice-room UI only needs four visual states for its mic/waveform indicator.
`connecting`, `idle` and `endpointing` all collapse to `listening` from the user's point of
view — there is no user-facing difference between "not talking yet" and "deciding if you're
done talking". `closed` has no live indicator (the session view changes entirely at that
point).

## Why this isn't a guess to be nervous about

Every field that references these enums does so through the generated Pydantic/TypeScript
types, so if Phase 1 needs a finer split (e.g. distinguishing `connecting` from `idle` in the
UI), it is a schema change caught by the `schema-drift` CI job — not a silent drift.
