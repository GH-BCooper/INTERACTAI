# Phase 4 — LEARN — Shell, onboarding and real users (days 16–17)

**Exit criterion:** a stranger can sign up, pass the audio check, complete a session and read a
report without help — and ten to fifteen recruited sessions have been run with consent.

**Study time this phase:** ~1 hour. There is almost nothing new to learn technically. This
phase is about **conversion, consent, and collecting the highest-quality third of your training
set.**

---

## 1. Day 17 is the constraint that cannot be compressed

> Recruited sessions need scheduling, consent, and a product that works well enough not to
> waste someone's time. If day 17 slips, Phase 5 slips with it, and the fine-tune — the most
> differentiating part of the whole project — gets squeezed.

You were told on day 12 to ask people and book them for day 17. If you did not, **stop reading
and do it now.** Everything else in this phase can be compressed; this cannot.

**Over-book by fifty per cent.** If you need ten sessions, book fifteen. People cancel, get
sick, forget, or turn up with a broken microphone. This is not pessimism, it is arithmetic.

---

## 2. Why recruited sessions are worth so much

They serve **three purposes simultaneously**, which is why they are the best-value hours in the
entire 24-day plan:

**1. The highest-fidelity third of your training set.** Real audio, real ASR errors, real
delivery artefacts, real nervousness, real accents that are not yours. Synthetic data can fill
the tails of the score distribution; it cannot produce the centre. Your own sessions are the
highest fidelity but the lowest volume — and they are all one speaker, which is a serious
problem for a model that must generalise across speakers.

**2. Genuine user testing.** You will watch ten people use a product you designed and be wrong
about something within the first three minutes. You cannot get that from a spec.

**3. The speaker diversity your splits depend on.** Phase 5 requires splitting by **session and
by speaker**, never by turn. If every session is you, there is no speaker to hold out and every
metric you report is inflated. Ten different voices is the minimum for a defensible split.

---

## 3. Consent is a real requirement, not a formality

You are recording someone's voice — which is **biometric data** — while they fail at something.
That is genuinely sensitive material, and the fact that they are your friend makes it more
important to get right, not less.

### What the consent form must actually say

- What is recorded (audio, transcript) and for how long it is kept.
- That the recording may be **used to train a model** — as a **separate, explicit,
  revocable** opt-in, never bundled into general terms acceptance.
- That transcripts are PII-scrubbed before any human annotator sees them.
- How to revoke, and that revocation genuinely deletes — including object storage.
- That the report is a measurement against a rubric you wrote, and **does not predict hiring
  outcomes**.

Two separate checkboxes: *"I consent to this session being recorded"* and *"I consent to my
anonymised transcript being used to train a scoring model"*. Someone may reasonably say yes to
the first and no to the second, and your data pipeline must respect that at the row level.

### Practical form

A one-page document they read and sign (digitally is fine) before the session, plus the in-app
toggle. Have it written and ready **before** day 17 — writing a consent form while someone
waits on a video call is not a good look and produces a worse form.

---

## 4. How to run a session so it produces usable data

### Before

- Send the scenario in advance so they arrive prepared. An unprepared participant produces
  answers clustered at the low end, which is not the distribution you need.
- Ask them to use **headphones** and a quiet room.
- Run the pre-flight audio check with them on the call before you start. A silent session is a
  wasted forty minutes of someone's goodwill.

### During

- **Say nothing.** The instinct to help is strong and it corrupts everything. If they are
  confused, note the confusion — that is the finding. Helping them past it deletes the finding.
- Note the exact moment of every hesitation, misunderstanding, or "wait, is it my turn?".
  Those notes are your usability findings and they are more valuable than anything they say
  afterwards.
- If something breaks badly, note it and continue if you can. A degraded session still produces
  labelled turns.

### After

Three questions, in this order:

1. *"At any point, did you forget you were talking to a computer?"* — the believability
   question. The answer is usually "for about ten seconds, when…" and that ten seconds tells
   you what is working.
2. *"Was there a moment you weren't sure what to do?"* — the usability question.
3. *"Would you do this again before a real interview?"* — the only retention signal you will
   get this early.

Write the answers down verbatim, immediately. You will not remember them accurately in an hour.

### Diversity to aim for

- Different accents and speaking rates — this is what your **fairness deltas** in Phase 6 will
  be computed across. Without variation you cannot detect accent bias, and "I didn't measure
  it" is a much weaker answer than "I measured it and here is the gap".
- Different experience levels, so the score distribution spans the scale.
- At least one non-native English speaker.
- At least one person who is genuinely bad at interviews. The low tail is real data you cannot
  synthesise convincingly.

---

## 5. The rule for day 17: fix only what blocks data collection

You will find ten things wrong. Fix **only** the ones that prevent the next participant from
completing a session and producing usable audio.

Everything else goes in a list for after Phase 5. The temptation to polish while people are
watching is enormous and it will cost you the training set.

Concretely:
- ✅ Fix: microphone check fails on Firefox, session crashes at 15 minutes, upload silently
  drops turns.
- ❌ Do not fix: the score panel spacing is off, the persona said something slightly odd once,
  the report loads in 1.4 s instead of 1 s.

---

## 6. Onboarding: five minutes to a completed first session

The success criterion for the whole flow is **a completed first session within five minutes of
signup.** Not a completed profile. Not a tour. A session.

Four steps with a progress rail:

1. **Goal** — what are you preparing for? **Three cards, not a form.** Cards are one click;
   forms are a decision plus typing plus a submit.
2. **Profile** — target role and experience level. Resume paste is offered and **explicitly
   optional, with the privacy consequence stated in one sentence.** Not buried in a link.
3. **Audio check** — microphone permission, device selection, a three-second speech test with
   the transcript shown, and a playback test.
4. **First session** — a five-minute scenario chosen for the stated goal, launched immediately.

### Why step 3 gets its own step

A first session that silently fails is an **unrecoverable first impression**. The user does not
conclude "my microphone is misconfigured"; they conclude "this doesn't work" and they never
come back.

The audio check tests capture → transport → ASR → playback, and shows the transcript back. That
last part matters: seeing your own words appear is the moment the product becomes credible.

### The front door rule

> If starting the first session takes longer than ninety seconds, the product has failed at its
> front door.

The scenario library exists so nobody has to write a prompt. The default entry point is a
curated, ready-to-run scenario. Custom authoring is P1 and sits at the end of the grid, not in
a separate menu.

---

## 7. The dashboard: designed for someone opening the tool to practise

Not to browse. The home page has one job: get them into a session.

- **A primary action block**: *continue where you left off*, or the recommended next scenario
  with a one-line reason — *"structure has been your weakest dimension for three sessions"*.
- **A progress strip** of four figures: sessions this week, total minutes, overall score with
  delta, weakest criterion.
- **The last five sessions.**
- **An attention panel** surfacing an unread report, a scenario attempted three times without
  improvement, or a criterion trending downward.
- **Empty state:** one call to action to run the first session. Nothing else.

The recommendation with a reason is worth more than a recommendation without one. "Try this
scenario" is noise; "structure has been your weakest dimension for three sessions" is a reason
to click.

---

## 8. Progress: filter by family or the numbers are meaningless

Score trend per criterion over time with session markers; practice volume by week; scenario
coverage; the weakest-dimension callout with a specific next action; a personal-best list.

**Filterable by scenario family, always.** Mixing negotiation and technical scores into one
trend line produces a number that means nothing — the rubrics are different, the criteria are
different, and the difficulty of a 4 differs between them.

The **weakest-dimension callout** should be chosen by *trend*, not just by lowest absolute
score. A criterion sitting at 5 but declining for three sessions is more urgent than one sitting
at 4 and stable.

---

## 9. PII scrubbing — build it before you have data to scrub

Sessions contain names, employers, salary figures, and voice. Before **any** transcript reaches
an annotation interface — including your own eyes on day 19 — it must be scrubbed of names,
employers and contact details.

Build this on day 16, not day 18. It is thirty minutes of work and doing it after you have
already read the transcripts defeats the purpose.

Note the honest limitation: automated PII scrubbing on conversational transcripts is imperfect,
especially for unusual names and company names that are also common nouns. Use a named-entity
model plus a manual review pass on the annotation set, and **say so** in your README rather
than claiming it is airtight.

---

## 10. Pitfalls

| Pitfall | Consequence | Prevention |
|---|---|---|
| Not booking on day 12 | Day 17 slips, fine-tune squeezed | Book fifteen for ten |
| Helping participants during a session | Usability findings deleted | Say nothing, write everything down |
| Polishing UI on day 17 | Lost training data you cannot re-collect | Fix only what blocks collection |
| Bundling training consent into terms | Ethically wrong; also legally shaky | Two separate checkboxes |
| Only recording yourself | No speaker holdout, every metric inflated | Ten different voices minimum |
| All participants are good at interviews | Score distribution has no low tail | Deliberately recruit a range |
| Onboarding that ends at a dashboard | Users never complete a first session | Onboarding ends **in** a session |
| PII scrubbing built on day 18 | You have already read unscrubbed data | Build it day 16 |

---

## 11. Interview questions this phase earns you

- *How did you get training data, and how did you handle consent?*
- *What did you learn from watching people use it that you couldn't have predicted?*
- *How do you make sure your evaluation isn't just measuring yourself?*
- *What is your speaker-holdout strategy and why does it matter?*

That third question is the one that separates people who ran a study from people who ran a
script.

---

## 12. Checklist before Phase 5

- [ ] Dashboard, scenario library, progress page, settings all working
- [ ] Onboarding gets a stranger from signup to a live session in under five minutes
- [ ] Audio check catches a broken microphone before the session, not during
- [ ] Consent form written, signed, stored — with training consent as a **separate** opt-in
- [ ] PII scrubbing implemented and tested
- [ ] **10–15 sessions completed with real people, at least 8 different speakers**
- [ ] Usability notes written up in `docs/PROGRESS.md`
- [ ] Session audio and transcripts stored, consent flags recorded per session at the row level

→ `phase-5-LEARN.md`
