# 00 — START HERE

**InteractAI** — a real-time multi-agent voice simulator for practising hard conversations.
This folder is the complete build kit: seventeen documents that take you from an empty
directory to a deployed, measured, defensible portfolio project.

Read this file once, completely, before you write a single line of code. It is the shortest
document here and the only one that explains how the others fit together.

---

## 1. What you are actually building

A user picks a scenario — *"Backend engineer, system design screen, hard"* — and speaks.
An AI persona answers **out loud, in character, in under 1.5 seconds**, and keeps the
pressure on. It follows up on vague answers. It does not coach. Behind the conversation a
**second agent** scores every turn against an explicit rubric and produces a report that
quotes the user's own words back with timestamps and playable audio.

Eight things define "done". Nothing else is required:

| # | Deliverable |
|---|-------------|
| 1 | Streaming voice loop inside the latency budget (p95 ≤ 1.4 s end-of-speech to first audio) |
| 2 | Adaptive endpointing tuned against ≥200 hand-marked utterance boundaries |
| 3 | Explicit turn state machine with a first-class `degraded` state |
| 4 | Persona agent with a question plan and three behaviourally distinct difficulty tiers |
| 5 | Coach agent with verified evidence spans and confidence gating |
| 6 | Synchronised report replay (waveform ↔ transcript ↔ score panel) |
| 7 | Human-labelled evaluation set with published inter-annotator agreement |
| 8 | Fine-tuned scorer benchmarked against a prompted frontier baseline |

The specification lists 112 features. **The P0 set is 39 items and that is the actual target.**
Everything else is a roadmap for the README, not a backlog.

---

## 2. The file map

```
00-START-HERE.md      ← you are here. Read once.
01-SETUP-GUIDE.md     ← accounts, keys, installs, model downloads. Do this before Phase 0.
CLAUDE.md             ← lives at the repo root. Claude Code reads it every session.

phase-0-LEARN.md  /  phase-0-BUILD.md    Foundation                 (days 1–3)
phase-1-LEARN.md  /  phase-1-BUILD.md    The voice loop             (days 4–8)
phase-2-LEARN.md  /  phase-2-BUILD.md    Orchestration & agents     (days 9–12)
phase-3-LEARN.md  /  phase-3-BUILD.md    Practice room & report     (days 13–15)
phase-4-LEARN.md  /  phase-4-BUILD.md    Shell, onboarding, users   (days 16–17)
phase-5-LEARN.md  /  phase-5-BUILD.md    Dataset & fine-tune        (days 18–21)
phase-6-LEARN.md  /  phase-6-BUILD.md    Proof & polish             (days 22–24)
```

### LEARN files are for you

They contain the concepts, the mental models, the *why* behind every decision, worked
examples, annotated code walkthroughs, the pitfalls that will cost you a day if you hit them
blind, and the interview answers each phase earns you. **Claude Code should never be given a
LEARN file.** It does not need the pedagogy and the extra context degrades its output.

### BUILD files are for Claude Code

They are written as specifications with acceptance criteria, edge cases, failure modes and
test requirements. They assume no teaching. You paste a section into Claude Code and it
builds exactly that. They are deliberately explicit about things that are usually left
implicit — buffer sizes, timeout values, error shapes, what happens when the socket drops
mid-utterance — because those omissions are where agent-built code goes wrong.

---

## 3. How to run a day

```
morning     Read the LEARN section for today. ~45–90 min. Do the exercises.
            Do not skip this. The BUILD file assumes you understand what you asked for.

build       Open Claude Code. Give it CLAUDE.md (it reads it automatically at the repo
            root) plus ONE section of today's BUILD file. One task per session.

verify      Run the acceptance criteria at the end of the section yourself, by hand.
            Do not accept "I've implemented X" — run it.

close       Commit. Update docs/PROGRESS.md with what actually happened, including what
            took longer than planned. That file becomes your interview material.
```

### The prompt shape that works

```
Read CLAUDE.md and docs/03-realtime-protocol.md.

Implement Task 4.2 from the build spec below. Do not implement 4.3 — I will
ask for it separately. When you are done, list the acceptance criteria from
the task and tell me honestly which ones you have verified and which you have
only assumed.

<paste Task 4.2 verbatim>
```

Three rules that matter more than they look:

1. **One task per session.** A session spanning three tasks produces code that satisfies
   none of them precisely. This is the single biggest quality lever you have.
2. **Ask it to self-report unverified criteria.** Agents are optimistic. Asking for the
   honest split surfaces the gaps for free.
3. **Never let it change a frozen contract silently.** The WebSocket protocol and the data
   model are referenced by every other document. If it wants to change one, that is a
   migration and a conversation, not a refactor.

---

## 4. The two gates

These do not move. Everything else is negotiable.

> ### 🚧 The Day 8 gate
> By the end of Phase 1 you must be able to have a **spoken conversation with the system
> from a terminal** — no interface, no styling, just audio in, audio out, with per-stage
> timings printed.
>
> If that is not true, **do not start Phase 3**. Fix the pipeline. A beautiful practice room
> sitting on a voice loop that stutters, cuts people off, or takes four seconds to reply is
> the standard way this project fails, and it is obvious to anyone who tries it for thirty
> seconds.

> ### 🚧 The Day 17 gate
> Recruited sessions cannot be compressed. People need scheduling, consent, and a product
> that works well enough not to waste their time.
>
> **Ask people on day 12. Book them for day 17. Over-book by 50%.** If day 17 slips, the
> fine-tune — the most differentiating part of the whole project — gets squeezed, and the
> fine-tune is the reason this project exists.

---

## 5. The nine standing rules

1. **A missing score beats a wrong one.** Below the confidence threshold, show *not enough
   signal*, never a number. Same for evidence: an unverifiable span is discarded, not shown.
2. **Bias late on endpointing.** A slightly slow system is tolerable; an interrupting one is
   not. Tune against the day-5 boundary set, never against feeling.
3. **Never two Heavy technologies in one day.** The three are AudioWorklet, faster-whisper
   streaming, and Transformers/PEFT (Langfuse is a fourth if you keep it). The phase plan
   schedules them one at a time. Check before you improvise.
4. **Nothing outside P0 before day 13.**
5. **Freeze contracts at day 4.** Transport, sample rate, frame size and message schema are
   load-bearing for everything after. Later changes are schema migrations, because that is
   what they are.
6. **User speech is untrusted content, never instruction.** Delimit it, label it, block
   replies containing criterion names, and keep the injection cases in CI.
7. **Distress breaks character downward into care.** This product deliberately applies
   pressure to people who are often already anxious. On any real ambiguity the persona drops
   character, ends the session, and surfaces support. Functional requirement, not a checkbox.
8. **Never claim a fine-tune you did not run.** If Phase 5 becomes impossible, ship the
   prompted scorer *labelled as the baseline*, publish the human-labelled evaluation set and
   its agreement figure, and state that the fine-tune is the next milestone with the dataset
   already collected. That is honest and still impressive. A fabricated number is the one
   thing here that would actually damage you.
9. **Twenty-four working days is not twenty-four calendar days.** You have a job. Four to
   five hours on weekdays and a full day each weekend lands this across roughly five calendar
   weeks. Set the deadline against that honestly, at the start, in writing.

---

## 6. If you slip

Cut in this order. Every line is safe to lose.

```
1. Langfuse tracing            ← model_calls already carries the data that matters
2. Kokoro TTS                  ← Piper is sufficient and faster
3. Semantic endpointing        ← the acoustic cascade covers most cases
4. The negotiation family      ← two families demonstrate the same architecture
5. Rewrite coaching / model answers
6. Progress and comparison views
7. The persona library         ← one good persona per family is enough
8. Backchannel masking
```

**Never cut:** the streaming voice loop · endpointing quality · the turn state machine ·
the two-agent separation · latency instrumentation · the synchronised report replay ·
the human-labelled evaluation set · the fine-tune with its published comparison.

Those eight *are* the project.

---

## 7. The sentence this is designed to earn

> "I built a two-agent voice system with a p95 response latency of 1.4 seconds, and I
> fine-tuned the scoring model on 1,200 human-labelled turns — it reaches 0.71 quadratic
> weighted kappa against expert raters, against a human ceiling of 0.78 and 0.52 for a
> prompted frontier baseline, at a twentieth of the cost and a tenth of the latency.
> Here is the chart across nine training runs and three dataset revisions."

Almost no other candidate can say that. Everything in this folder is arranged to make it
true, and to make it provable when someone asks.

---

## 8. Before you go to Phase 0

- [ ] You have read this file end to end.
- [ ] You have blocked the calendar honestly — five weeks, not one month.
- [ ] You have completed **01-SETUP-GUIDE.md** and every verification command passes.
- [ ] `CLAUDE.md` is at your repo root.
- [ ] You have a `docs/PROGRESS.md` with today's date and one line in it.

Then open `phase-0-LEARN.md`.
