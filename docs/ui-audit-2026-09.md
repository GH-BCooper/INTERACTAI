# UI / product audit — September 2026

A read-through of every route in `apps/web` and the public API surface in `services/api`,
listing everything that could be fixed, finished or improved to make InteractAI feel premium.
**Status (2026-09-30): implemented** — see "Implementation status" at the end for the few items
that were deliberately scoped differently, and why. Each item names its file so it can be picked up
as a standalone task.

Priority key: **P0** = broken or visibly unfinished · **P1** = polish a reviewer will notice · **P2** = nice to have.

Constraints that every item below must respect (from CLAUDE.md and `globals.css`): six type
sizes, two weights, one accent colour, and `--score-*` tokens used only for rubric values.
"Premium" here has to come from spacing, hierarchy, motion and completeness, not from new
colours or gradients.

---

## 1. Cross-cutting (affects every page)

| # | Pri | Issue | Where | Fix |
|---|---|---|---|---|
| 1.1 | P0 | **No `error.tsx`, `loading.tsx`, `not-found.tsx` or `global-error.tsx` anywhere.** An unhandled throw shows the raw Next.js error page, and an unknown URL shows the default 404. This breaks CLAUDE.md §6 ("never a stack trace"). | `apps/web/app/**` | Add branded boundaries at the root, at `/app`, and at `/app/(bare)/practice`. Use the §6 error shape (code, message, recovery). |
| 1.2 | P0 | **Buttons nested inside links** (`<a><Button>` / `<Link><Button>`). This is invalid HTML, produces a double tab stop, and screen readers announce both. | `app/app/(shell)/page.tsx:18,85`, `top-bar.tsx:50`, `scenarios/custom/page.tsx:15` | Give `Button` an `asChild`/`href` variant, or style the link itself as a button. |
| 1.3 | P0 | **Internal navigation uses `<a href>` instead of `<Link>`** (11 places). Every click reloads the whole page, drops TanStack Query's cache and re-runs the auth bootstrap, so the app feels slow. | dashboard, sessions, progress, scenarios, settings tabs (`settings/layout.tsx:25`), onboarding, evals | Replace with `next/link`. |
| 1.4 | P0 | **No favicon, app icon or OG image.** `public/` has no `favicon.ico`, `icon.png` or `opengraph-image`, so shared links render a blank card. | `apps/web/app/` | Add `icon.svg`, `apple-icon.png` and `opengraph-image.tsx` (the landing page could render dynamically from `published-metrics.json`). |
| 1.5 | P1 | **Every browser tab title is "InteractAI".** Only the root layout and `/demo` export `metadata`. | all `page.tsx` | Add a `title.template` of `"%s · InteractAI"` plus a title on each route. Client pages need a server `layout.tsx` wrapper for this. |
| 1.6 | P1 | **No mobile layout for the app shell.** The sidebar is always `w-56`/`w-16`, with no drawer or breakpoint, so at 375px the content gets about 300px. | `components/shell/sidebar.tsx:57` | Below `md`, hide the sidebar behind a hamburger drawer (or add a bottom tab bar). |
| 1.7 | P1 | **Modals have no focus trap, no scroll lock and no enter/exit motion.** They also don't return focus to whatever opened them. | `start-session-dialog.tsx`, `end-session-dialog.tsx`, `consent-screen.tsx`, `command-palette.tsx` | Build one shared `<Dialog>` primitive (Radix Dialog, or native `<dialog>`) with a 150ms fade and scale using `--motion-ease`. |
| 1.8 | P1 | **Only one UI primitive exists** (`Button`). Selects, inputs, checkboxes, tabs, pills, cards and skeletons are restyled by hand on every page, and the differences show (e.g. `bg-page` vs `bg-card` on selects). | `components/ui/` | Extract `Input`, `Select`, `Checkbox`/`Switch`, `Tabs`, `Pill`, `Card`, `Skeleton` and `EmptyState`. This is the biggest single win for consistency. |
| 1.9 | P1 | **Off-scale font sizes** (`text-[10px]`, `text-[11px]`) break the "exactly six sizes" token rule. | `app/page.tsx:62,126`, `progress/page.tsx:124`, `top-bar.tsx:46` | Use `text-xs`. |
| 1.10 | P1 | **Dates are formatted inconsistently and can mismatch on hydration.** Raw `toLocaleDateString()` / `toLocaleString()` is used, even though a `LocalDate` component already exists for this. | dashboard, sessions, command palette, progress, `scenarios/[id]` | Use `LocalDate` everywhere, plus relative times ("2 days ago") in lists. |
| 1.11 | P2 | **The toast has no enter/exit animation, no variants** (success/error), and a fixed `w-80` that overflows on small phones. | `components/shell/toast-region.tsx` | Add a slide-in, variants and `max-w-[calc(100vw-2rem)]`. |
| 1.12 | P2 | **Skeletons don't match the final layout** (e.g. the dashboard skeleton has no heading), so the page visibly jumps when data loads. | dashboard, progress, sessions | Match the real layout's dimensions. |
| 1.13 | P2 | **No page-transition or list-stagger motion.** The app feels static. | global | Add a subtle 150ms fade on route change and on list mount. Respect reduced motion, which is already handled globally. |

## 2. Public surface

### Landing — `app/page.tsx`
- **P1** The hero is text only. There is no product visual above the fold. Move the audio proof strip, or a screenshot of the practice room, into the hero.
- **P1** The header has no logo mark, just the word "InteractAI" in `text-sm`. Add a wordmark and a sticky header with a blur on scroll.
- **P1** The metric callout reads "not yet measured" three or four times when `published-metrics.json` is empty. The copy is honest, but visually it looks broken. When a run is null, collapse it into a single "Evaluation runs pending" card (never a fake number; see CLAUDE.md §1.10).
- **P2** No FAQ, scenario showcase or "who it's for" section. The footer has no privacy or terms links.

### Sign in — `app/signin/page.tsx`
- **P1** Very bare: no logo, no provider icons (GitHub and Google marks), no split layout, no privacy/terms line, and GitHub and Google get inconsistent primary/secondary weights.
- **P1** No error state. If `/auth/callback` fails, the user needs a readable message here (`?error=`).
- **P2** No "back to home" link.

### Demo — `app/demo/page.tsx`
- **P2** Add a persistent "Sign in to try it yourself" CTA bar. Right now the demo is a dead end.

## 3. Onboarding — `app/onboarding/page.tsx`
- **P1** The progress rail is three bare bars with no step labels or "Step 2 of 3". Add labels and a back button between steps.
- **P1** The resume field is a raw textarea. Add a character counter and a note that the text is scrubbed/private (per the PII rules).
- **P2** Animate between steps (a slide at the 400ms panel motion token).

## 4. App shell

### Sidebar — `components/shell/sidebar.tsx`
- **P1** When collapsed, labels vanish with no tooltip. Add `title` or a tooltip to each nav item.
- **P1** The admin items are mixed into the main list. Put them in a labelled "Admin" group with a divider.
- **P1** The weekly-minutes meter is plain text. Make it a small progress ring or bar against a weekly goal, if the profile has one; otherwise keep it as text.
- **P2** Persist the collapsed state (check `shell-store`) and add a keyboard shortcut (`[`).

### Top bar — `components/shell/top-bar.tsx`
- **P1** The breadcrumb is a single string. Admin routes (`/annotate`, `/observability`, `/evals`) and settings sub-tabs fall through to "InteractAI" or "Settings". Show a real trail (Scenarios › *Title*), taken from the route plus the loaded entity name.
- **P1** The ⌘K hint is hard-coded, so Windows users see ⌘. Detect the platform and show `Ctrl K`.

### Command palette — `components/shell/command-palette.tsx`
- **P1** Sessions are listed as "Session from 9/28/2026", which is useless. Show the scenario title and score.
- **P1** It has no navigation entries (Progress, History, individual Settings tabs) and no icons or shortcuts on items.
- **P2** Keep the palette mounted and animate it open instead of unmounting (`if (!open) return null`), so the search input keeps its state.

## 5. Dashboard — `app/app/(shell)/page.tsx`
- **P0** The primary card is an `<a>` wrapping a `<Button>` (see 1.2).
- **P1** The stat tiles are flat boxes with no trend context. Add a sparkline to "Overall score" (the `Sparkline` component already exists) and "vs last week" to minutes.
- **P1** "Weakest criterion" shows only the criterion name. Make it link to the matching Progress filter.
- **P1** The recent-sessions list says "· unread" as plain text. Use a dot badge instead.
- **P2** The empty state has no illustration. Consider an inline "Start your first 5-minute session" that opens the start dialog directly, instead of routing to the library.

## 6. Scenario library — `app/app/(shell)/scenarios/page.tsx`
- **P1** Cards show only the family, title, difficulty and length. There is no brief, persona name/avatar or tags, so every card looks the same. `ScenarioOut` probably already carries this; check before adding fields.
- **P1** Difficulty is shown raw and lowercase ("hard"). Capitalise it and render a three-step difficulty indicator.
- **P1** The tag filter calls `router.replace` on every keystroke. Debounce it (about 250ms).
- **P1** The filters mix pill tabs with native `<select>`s. Make them all pills or all dropdowns (depends on 1.8).
- **P1** The "Custom scenario" card is advertised in the grid but leads to a "coming soon" page (`scenarios/custom/page.tsx`), and `POST /scenarios` returns 501. Either hide the card until P1 authoring ships, or style it as clearly disabled with a "Soon" pill. An advertised dead end hurts the premium feel.
- **P2** Add a search box that uses the same fuzzy match as the command palette.

### Start-session dialog — `components/dashboard/start-session-dialog.tsx`
- **P1** Difficulty and duration are native selects. Use segmented controls (four durations and three difficulties fit easily).
- **P1** No preview of what's coming: persona, a one-line brief, number of questions. This is the moment of commitment.
- **P1** The "recruited/research session" checkbox is shown to every user. It's a research-only affordance, so gate it behind a flag or an admin check.
- **P2** Add a voice preview button (`lib/audio/voice-preview.ts` already exists).

## 7. Practice room — `components/practice/*`
This is the demo-critical surface, so these items carry the most weight.
- **P0** The timer drifts and resets. `setInterval(+1000)` accumulates drift and restarts at 0 after a reload or reconnect. Derive elapsed time from the session start timestamp instead (`practice-room.tsx:125`).
- **P1** The reconnecting pill uses `--danger`, which is reserved for destructive actions. Use `--status-bad` (`practice-room.tsx:220`).
- **P1** The persona avatar is a single initial in a circle. A generated monogram with a subtle gradient ring is not possible under the tokens, so use a persona portrait or a distinct glyph per persona from `content/personas`.
- **P1** The state label ("Your turn / Thinking / Speaking") appears only under reduced motion. Show it always, small and under the name. Motion alone is not an accessible state signal.
- **P1** "Loading your session…" is plain text on a blank page. Use a skeleton of the room layout so there's no jump when it becomes live.
- **P1** No visible elapsed/remaining progress around the presence ring. A thin progress arc against `target_minutes` would feel premium and costs nothing on the latency path.
- **P2** Keyboard shortcuts (M mute, C captions, Esc end), shown in the controls' tooltips.
- **P2** The "Session saved" overlay could show a short summary (turns, minutes) while it redirects.

## 8. Session history — `app/app/(shell)/sessions/page.tsx`
- **P0** Rows show only a timestamp and a raw uppercase status (`CLOSED`). There's no scenario title, score, duration or difficulty, so the list is not scannable. It needs `scenario_title` / `overall_score` on `SessionOut`, or a list-specific schema. The dashboard's `recent_sessions` already has these fields, so reuse that query.
- **P1** Status should be a styled pill ("Completed", "In progress", "Scoring…").
- **P1** No filters (family, date range) and no search.
- **P2** Group rows by week or month with sticky headers.

## 9. Report — `components/report/*`
- **P0** The **Share**, **Export** and **Delete recording** buttons are permanently disabled ("Coming soon") on every report (`report-header.tsx:79-87`). No backend endpoint exists for any of them.
  - Delete recording is a privacy commitment (CLAUDE.md §10: "Deletion is genuine, including object storage"). Build `DELETE /sessions/{id}/recording`.
  - Export: add `GET /sessions/{id}/export` (JSON/PDF). `/me/export` already exists for the whole account.
  - Share: needs a signed read-only link, which is a real design question. Until it ships, hide the button instead of showing it disabled.
- **P1** The overall score is a small `ScoreBadge` at `text-sm`. The hero number should use `text-xl` (the token comment already reserves 32px "for hero numbers").
- **P1** "Report not found." is a bare line of text. Use a proper empty state with a way back.
- **P1** While the coach is still scoring (`pollWhilePending`), the verdict shows a grey skeleton indefinitely. Show an explicit "Scoring your answers — usually under a minute" state with progress.
- **P2** Add a sticky mini-player so the waveform controls stay reachable while reading the transcript.
- **P2** Add a section jump nav (Verdict · Scores · Delivery · Transcript).

## 10. Progress — `app/app/(shell)/progress/page.tsx`
- **P1** The weekly volume chart is hand-drawn divs with no axis, gridline or value labels, and the hover tooltip is only a `title`. Replace it with a proper small bar chart with a hover state.
- **P1** A sparkline with only one point renders as nothing. Show "1 session — need 2+ for a trend".
- **P1** The family tabs don't include an "All" option.
- **P2** Scenario coverage pills could link into the filtered library.

## 11. Settings — `app/app/(shell)/settings/*`
- **P0** The **Notifications** tab has two disabled checkboxes and nothing else (`settings/notifications/page.tsx`). Remove the tab until notifications exist.
- **P1** The tabs use `<a>` (full reload) and overflow horizontally on mobile. Use `Link` and a scrollable tab strip.
- **P1** Save feedback: check that Profile, Audio and Models all show saving/saved states. Profile duplicates the onboarding fields, so extract a shared form.
- **P1** Privacy: "Delete account" (`DELETE /me`) should be a typed-confirmation danger zone, visually separated from the rest.
- **P2** Models (BYOK): mask saved keys, show last-tested time, and use status pills with `--status-ok` / `--status-bad`.

## 12. Admin — annotate / observability / evals
- **P1** No shared page chrome (title, description, date-range picker) across the three. Observability and Evals are dashboards and should share one filter bar.
- **P1** Every admin route needs empty states for "no eval runs yet" and "no latency events".
- **P2** Annotate: keyboard-first scoring (1–5 keys, J/K to move between items) and a progress bar for the round.

## 13. Backend gaps that block UI items

| Gap | Blocks |
|---|---|
| `DELETE /sessions/{id}/recording` (including MinIO object) | 9 — Delete recording (privacy requirement) |
| `GET /sessions/{id}/export` | 9 — Export |
| Session list lacks scenario title and overall score | 8 — History rows, 4 — Command palette |
| `POST /scenarios` returns 501 | 6 — Custom scenario card |
| No signed share-link model | 9 — Share |

---

## Suggested order
1. **Correctness and completeness (P0):** 1.1, 1.2, 1.3, 1.4, 7 timer, 8 history rows, 9 disabled buttons, 11 notifications tab.
2. **Primitives (1.8) and Dialog (1.7).** Most P1 visual items get faster once these exist.
3. **Page polish, in demo order:** practice room → report → dashboard → library → landing/sign-in.
4. **Mobile shell (1.6).**

---

## Implementation status (2026-09-30)

Everything above is implemented, verified by `pnpm run lint` (eslint + token + contrast gates),
`tsc --noEmit`, vitest, `next build`, the API integration suite, and a live browser pass against a
local stack. These items landed differently from the suggestion, on purpose:

| Item | What shipped | Why |
|---|---|---|
| 9 Export | `GET /sessions/{id}/export`, JSON only | A PDF renderer is a new dependency for a second format of the same data; JSON matches `/me/export`. |
| 9 Share | Button removed, not disabled | Signed read-only links are still an open design question (no share-link model). |
| 6 Custom scenario | Non-link card marked "Soon"; old URL kept as an honest page | `POST /scenarios` is still 501. |
| 6 Start dialog "number of questions" | Not shown | `ScenarioOut` doesn't carry the question plan, and a guessed count would be a fabricated number. |
| 4 Weekly-minutes meter | Stays a number | The profile has no weekly goal, so a progress bar would need an invented target (CLAUDE.md §1.10). |
| 7 Persona avatar | A distinct glyph per persona archetype | The tokens allow no gradients, and there are no portrait assets. |
| 1.4 OG image | Brand card with no metrics | A latency figure without its host class and dataset revision would mislead; the landing page shows the sourced numbers. |
| 6 Research checkbox | Admin-only | Recruited sessions are run by an admin. |
| 10 Family tabs "All" | `GET /me/progress?family=all` (explicit only) | The default is still the most-practised family, per Task 4.4. |

Also fixed while verifying: titles set by intermediate layouts dropped the `%s · InteractAI`
template for their child routes; and the report page polled a permanent 404 indefinitely for an
unknown or unfinished session (the report query is now gated on the session having ended).
