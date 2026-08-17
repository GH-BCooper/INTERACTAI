# Phase 4 — BUILD — Shell, onboarding and real users (days 16–17)

Build specification for Claude Code. Read `CLAUDE.md`, `docs/10-frontend-shell.md` and
`docs/17-security-privacy.md` first.

**Exit criterion:** a stranger completes signup → audio check → session → report without help.
Ten to fifteen recruited sessions run with consent.

**Day 17 is immovable.** Everything built on day 16 exists to make day 17 productive.

---

## TASK 4.1 — Dashboard (`/app`)

Audience: someone opening the tool to practise, not to browse.

### Sections

1. **Primary action block** — *continue where you left off* (if a session is incomplete) or the
   recommended next scenario **with a one-line reason**: *"structure has been your weakest
   dimension for three sessions"*. The reason is required, not decorative — a recommendation
   without a reason is noise.
2. **Progress strip** — four figures: sessions this week, total minutes, overall score with
   delta, weakest criterion.
3. **Last five sessions** — scenario, date, duration, overall score, report-read status.
4. **Attention panel** — surfaces exactly one of: an unread report, a scenario attempted three
   times without improvement, or a criterion trending downward. Empty if none apply; do not
   invent something to fill it.

### Empty state

One call to action to run the first session. No dashboard chrome, no zeros, no empty charts.

### Recommendation logic

Deterministic and explainable — **no model call**:

```
1. incomplete session exists                        → continue it
2. weakest criterion by 3-session trend             → scenario family exercising it
3. scenario family never attempted                  → that family, standard difficulty
4. last scenario, one difficulty tier up            → progression
5. fallback                                         → the onboarding-goal default
```

### Acceptance criteria

- [ ] Loads in < 500 ms (server-rendered)
- [ ] Recommendation always carries a human-readable reason
- [ ] Attention panel shows at most one item and is absent when nothing qualifies
- [ ] Empty state renders for a brand-new user with no zeros or empty charts

---

## TASK 4.2 — Scenario library and detail

### Library (`/app/scenarios`)

- Filter by family, difficulty, duration, tag.
- Cards show: persona avatar and name, one-line brief, difficulty, expected duration, rubric
  name, and **the user's own best score if attempted**.
- A prominent **Custom scenario** entry sits at the end of the grid, not in a separate menu.
  (P1 — the card renders and links to a "coming soon" state; do not build the authoring flow.)

### Detail (`/app/scenarios/[id]`)

**Left:** the brief, the persona description, **the rubric criteria with their anchor
descriptors**, and previous attempts with scores.

**Right:** a launch panel — difficulty, duration (5/10/20/30), focus areas, voice preview — with
a single **Start** button.

> **The rubric is shown before the session deliberately.** The user should know what they are
> being judged on. The persona still will not reveal it during the conversation. These are
> different things and both are correct: knowing the criteria in advance is fair; being told
> your score mid-interview is not realistic.

### Acceptance criteria

- [ ] All filter combinations work and are URL-encoded
- [ ] Voice preview plays a pre-synthesised sample without starting a session
- [ ] Start creates a session and navigates to the practice room in one click
- [ ] Anchor descriptors are visible on the detail page
- [ ] Previous attempts show with scores and link to their reports

---

## TASK 4.3 — Onboarding (`/onboarding`)

**Success criterion: a completed first session within five minutes of signup.** Not a completed
profile — a session.

### Four steps with a progress rail

**1. Goal.** *What are you preparing for?* **Three cards, not a form.** One click each.

**2. Profile.** Target role and experience level. Resume paste is **explicitly optional, with
the privacy consequence stated in one sentence inline** — not behind a link, not in a tooltip.

**3. Audio check.** This step exists because a first session that silently fails is an
unrecoverable first impression. It must verify the full chain:
- microphone permission (requested here, with the reason stated first — never on page load)
- device selection
- a three-second speech test **with the transcript shown back**
- a playback test with a "did you hear that?" confirmation

Failure at any point gives **browser-specific recovery instructions** and does not let the user
proceed with a broken setup.

**4. First session.** A five-minute scenario chosen for the stated goal, **launched
immediately.** Onboarding ends inside the practice room, not on a dashboard.

### Edge cases

| Case | Required behaviour |
|---|---|
| User abandons at step 2 | Progress saved; resuming returns to step 2 |
| Mic denied at step 3 | Cannot proceed; browser-specific instructions; a "skip for now" that clearly explains they cannot practise yet |
| ASR returns nothing on the test | Treat as failure; suggest a quieter room or a different device |
| Playback inaudible | Offer device selection; do not assume the default output |
| User already onboarded | Redirect to `/app` |

### Acceptance criteria

- [ ] A stranger, unaided, goes from signup to speaking in a session in under five minutes
      (**test this with an actual person, not by clicking through yourself**)
- [ ] The audio check catches a muted microphone and a wrong output device
- [ ] Transcript is shown back on the speech test
- [ ] Abandoning and returning resumes at the right step
- [ ] Onboarding ends in the practice room

---

## TASK 4.4 — Progress (`/app/progress`) and settings

### Progress

- Score trend per criterion over time with session markers
- Practice volume by week
- Scenario coverage — which families attempted, which not
- **Weakest-dimension callout with a specific next action**, chosen by **trend, not lowest
  absolute score**. A criterion at 5 and declining is more urgent than one at 4 and stable.
- Personal-best list

**Filterable by scenario family, always.** Mixing negotiation and technical scores into one
trend line is meaningless — different rubrics, different criteria, different meaning of a 4.
The default filter is the most-practised family, never "all".

### Settings (`/app/settings/*`)

| Section | Contents |
|---|---|
| Profile | Name, target role, experience, focus areas, resume text **with a prominent delete control** |
| Audio | Input/output device, echo cancellation and noise suppression toggles, persona speaking rate, captions default, **a re-runnable audio check** |
| Privacy | Audio retention window, **training-data consent with its own explicit toggle**, one-click export, one-click account deletion |
| Models | Provider credentials (bring-your-own-key), routing policy per logical role, local vs hosted preference, **a connection test per provider** |
| Notifications | Report-ready and weekly-summary channels |

### Privacy requirements (AS-03, AS-04, AS-05)

- Default retention 30 days, configurable down to **"delete immediately after scoring"**.
- Training consent is a **separate, revocable toggle**. **Never bundled into terms acceptance.**
  Revoking removes the user's turns from the annotation pool and from any future training
  dataset revision.
- One-click deletion removes the account and **all** artefacts, with object storage purged and
  confirmed — not marked-deleted.
- Export produces a JSON archive of profile, sessions, transcripts and scores.

### Acceptance criteria

- [ ] Progress defaults to a single family filter, never "all"
- [ ] Weakest-dimension callout uses trend, not absolute score (test with fixture data where
      these disagree)
- [ ] Retention setting is honoured by the expiry job
- [ ] Revoking training consent removes the user's turns from the annotation pool
- [ ] Deletion purges object storage; a test asserts zero remaining objects under the user prefix
- [ ] Provider connection test reports success and failure accurately

---

## TASK 4.5 — Consent flow and PII scrubbing ⚠️ BUILD BEFORE DAY 17

### 4.5a — Consent

- A consent record per session: `recording_consent` and `training_consent` as **two separate
  booleans**, timestamped, with the consent text version stored.
- The recruited-session flow presents the consent screen **before** the audio check.
- Training consent revocation cascades: turns are flagged `training_excluded = true` and are
  filtered out of every dataset build. **A revocation after a dataset revision has been built
  must be reflected in the next revision**, and the exclusion must be logged.

### 4.5b — PII scrubbing (AS-06)

`services/coach/app/privacy/scrub.py` — runs before **any** transcript reaches an annotation
interface, including your own.

- Named-entity recognition for `PERSON`, `ORG`, `GPE`, plus regex for emails, phone numbers and
  explicit salary figures.
- Replaces with stable pseudonyms within a session (`[PERSON_1]` refers to the same person
  throughout) so the transcript stays readable and scoreable.
- The **original is retained**, encrypted, and only the scrubbed version is shown in the
  annotation interface.
- **Document the honest limitation** in the README: automated scrubbing on conversational
  transcripts is imperfect, particularly for unusual names and company names that are also
  common nouns. A manual review pass over the annotation set is required and should be stated
  rather than glossed over.

### Acceptance criteria

- [ ] Two separate consent booleans, stored with a text version
- [ ] Revoking training consent excludes turns from the next dataset build (asserted by a test)
- [ ] PII scrubber catches names, employers, emails, phones and salary figures on a fixture
- [ ] Pseudonyms are stable within a session
- [ ] The annotation interface **only ever** receives scrubbed text
- [ ] Original text is retained and access-controlled

---

## TASK 4.6 — Day 17: recruited sessions

**Not a coding task.** The build for this day is: fix only what blocks data collection.

### Before the day

- [ ] 15 people booked (for a target of 10)
- [ ] Consent form written and ready to sign
- [ ] Scenarios sent in advance so participants arrive prepared
- [ ] Pre-flight audio check tested on Chrome and Firefox, macOS and Windows
- [ ] A note-taking template ready

### During each session

1. Consent signed before anything else.
2. Pre-flight audio check run **with them**, on the call, before the session starts.
3. **Say nothing during the session.** Note every hesitation, misunderstanding and "wait, is it
   my turn?". Those notes are the findings; helping them past a confusion deletes the finding.
4. Three questions afterwards, verbatim:
   - *"At any point, did you forget you were talking to a computer?"*
   - *"Was there a moment you weren't sure what to do?"*
   - *"Would you do this again before a real interview?"*

### The rule for the day

**Fix only what blocks the next participant from completing a session and producing usable
audio.** Everything else goes on a list for after Phase 5.

✅ Fix: crashes, upload failures, the audio check failing on a browser someone is using.
❌ Do not fix: spacing, wording, a persona reply that was slightly odd once, load time.

### Diversity targets

- ≥ 8 distinct speakers
- ≥ 1 non-native English speaker
- A range of experience levels so the score distribution spans the scale
- At least one person who is genuinely bad at interviews — the low tail is real data you cannot
  synthesise convincingly

### Acceptance criteria

- [ ] ≥ 10 sessions completed, ≥ 8 distinct speakers
- [ ] Every session has a signed consent record with both flags set explicitly
- [ ] All audio and transcripts stored and retrievable
- [ ] Usability notes written up in `docs/PROGRESS.md` the same day
- [ ] A prioritised bug list exists, with everything non-blocking deferred past Phase 5

---

## Phase 4 definition of done

- [ ] Dashboard, scenario library, scenario detail, progress and settings all working
- [ ] Onboarding takes a stranger from signup to speaking in under five minutes, verified with
      a real person
- [ ] Consent recorded as two separate, revocable flags
- [ ] PII scrubbing working and tested; limitations documented honestly
- [ ] **10–15 recruited sessions completed, ≥ 8 distinct speakers**
- [ ] Findings written up; non-blocking fixes deferred

> The most valuable output of this phase is not code. It is roughly 400–600 real user turns
> from eight or more speakers, with consent. Phase 5 cannot proceed without them.
