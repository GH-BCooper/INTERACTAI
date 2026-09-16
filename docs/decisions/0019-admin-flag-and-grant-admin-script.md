# 0019 — A single `is_admin` boolean, granted only by a local script

**Context.** Task 5.3a requires `/app/annotate` to be "admin only." No role system exists
anywhere else in this project — every other authorization decision in the codebase is either
"authenticated" or "owns this resource" (session ownership, profile ownership). Phase 5 is the
first place anything needs a third tier.

**Decision.** Add exactly one column, `users.is_admin: bool`, default `false`. No roles table, no
permission matrix, no invite flow. The only way to set it is `scripts/grant_admin.py`, a local
script that requires direct database access (the same trust boundary every other one-off
maintenance script in `scripts/` already operates under — `scripts/expire_recordings.py`,
`scripts/seed.py`). There is deliberately no API endpoint that can grant admin, at any
permission level — an admin-granting-admin endpoint is a privilege-escalation surface this
project has no product reason to carry.

**Why not more.** A full role system (reviewer / annotator / adjudicator / super-admin) would be
more "correct" in the abstract, but nothing in Phase 5's actual acceptance criteria needs more
than one bit: "can this account see `/admin/annotate` and `/admin/registry`, yes or no." Building
more than that now would be exactly the kind of speculative feature CLAUDE.md §13 asks not to
build ("do not implement beyond what was asked").

**Consequence.** Anyone who needs to annotate or manage the model registry needs the project
owner (or someone with database access) to run `grant_admin.py` for them. This is fine at the
project's current scale — a handful of annotators, per docs/PHASE5-WALKTHROUGH.md — and would be
the first thing to revisit if annotation ever needed to scale to a real annotation team with
its own onboarding flow.
