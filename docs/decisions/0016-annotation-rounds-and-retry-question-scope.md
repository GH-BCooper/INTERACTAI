# 0016 — Annotation rounds auto-increment; retry-one-question overrides only `opening_strategy`

**Phase:** 3, Task 3.4e/3.4f.

## Annotation rounds

`annotations` is unique on `(turn_id, annotator_id, criterion_key, round)` (Phase 0) specifically
so the same reviewer can label the same turn more than once across separate visits — CLAUDE.md
§5: "so the same item can be labelled independently more than once." `POST
/sessions/{id}/annotations` (`AnnotationCreate`) never accepts a `round` from the client; the
server looks up `MAX(round)` for that exact `(turn_id, annotator_id, criterion_key)` and inserts
`+1`. The alternative — letting the client pass `round` — would need the client to track its own
"which round am I on" state per turn per criterion, correctly, forever, with no server-side
guard against it drifting; auto-incrementing server-side makes the uniqueness constraint
un-violatable by construction rather than by client discipline.

## Retry-one-question's scope

`create_retry_session` (`services/api/app/services/session_service.py`) copies the *entire*
frozen `brief` from the original session and overrides exactly two fields: `opening_strategy`
(set to the text of the persona turn immediately preceding the retried answer — found the same
way `services/coach/app/report/build.py::_find_preceding_question` does, reimplemented rather
than imported since api and coach are independent workspace members) and `target_minutes` (fixed
at 5, the shortest tier). Everything else — persona, rubric, difficulty, difficulty_params,
resume snapshot — carries over unchanged, so "the same scenario, at the same difficulty" (Task
3.4f's own wording) is true by construction, not by re-deriving those fields a second time.

This makes the scripted opening line (Task 2.3f, `services/realtime/app/persona/opening.py`)
ask exactly the retried question, with **no changes to services/realtime's persona pipeline at
all** — the retry session is, from the realtime service's point of view, an entirely ordinary
session whose scenario happens to open on a specific line. If the user keeps talking past that
one question, the session continues normally rather than hard-stopping after one exchange; a
literal "exactly one question, then end" mode would need new state-machine behavior in
`services/realtime`, which this decision deliberately doesn't add — Task 3.4f asks for "a short
new session seeded with that one question," not a constrained single-turn mode.

## A related gap, not fixed here

`GET/POST /sessions/{id}/...`'s ownership check (`_get_owned_or_raise`,
`services/api/app/routers/sessions.py`, unchanged from Phase 0) returns `403 FORBIDDEN` for a
non-owner, not `404`. The WS handshake's own equivalent check
(`services/realtime/app/handshake.py`) deliberately collapses wrong-owner into the *same*
`NOT_FOUND` as a nonexistent session, with the explicit reasoning "confirming a session exists
to someone who doesn't own it is its own information leak." The REST side never got that
treatment in Phase 0. `apps/web` papers over this by rendering the identical "not found" message
for both statuses (`components/practice/practice-room.tsx`,
`components/report/report-view.tsx`), so the user-visible behavior matches the spec's "Not the
session owner -> 404" either way — but the API itself still leaks session-existence to a
non-owner via status code. Worth a real fix; not done here since it touches Phase 0's
already-tested authorization code path and wasn't asked for.
