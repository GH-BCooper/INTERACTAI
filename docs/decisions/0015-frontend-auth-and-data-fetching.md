# 0015 — Access token in memory, refresh in an httpOnly cookie; `/app/*` data fetching is
client-side

**Phase:** 3, Task 3.1.

## The auth model

- **Access token: in-memory only** (`apps/web/stores/auth-store.ts`, a Zustand store, never
  persisted to `localStorage`). It's 15 minutes, and a closed tab genuinely forgets it. An XSS
  payload gains nothing more from this than it already would from reading React/Zustand state
  directly — there's no persistence layer to make the exposure worse.
- **Refresh token: the existing httpOnly cookie** services/api/app/routers/auth.py already sets,
  unchanged from Phase 0 (`path=/auth`, `samesite=lax`). `apps/web/lib/api/client.ts` exchanges
  it for a fresh access token via `POST /auth/refresh` (`credentials: "include"`) once on app
  boot, and again, once, automatically on any `401` — never a retry loop.
- `localhost:3000` and `localhost:8000` are different *origins* but the same *site* (SameSite
  is defined on the registrable domain, not the port), so the `Lax` cookie is sent on the
  cross-origin `fetch` calls this architecture makes. **This does not hold across genuinely
  different domains** — a production deployment with `app.example.com` calling
  `api.example.com` needs `SameSite=None; Secure` on that cookie, which
  `services/api/app/routers/auth.py`'s `_set_refresh_cookie` does not set today. Flagged here,
  not fixed — it's a Phase 6 deployment-topology concern, not something to guess at now.

## Why client-side fetching, not literal Server Components fetching session data

`docs/phase-3-BUILD.md`'s own sketch shows `app/app/practice/[sessionId]/page.tsx` as "Server
Component — fetches session, scenario, persona." Taken completely literally, that would need
Next.js's Node server to carry the caller's access token into a server-to-server fetch against
`services/api` — which means either forwarding a second, SSR-readable cookie (real complexity:
a non-httpOnly access-token cookie, kept in sync with the in-memory store, on top of the
already-real httpOnly refresh cookie) or re-deriving auth server-side entirely.

The practice room needs a live `WebSocket` and `getUserMedia` regardless — both are browser-only
APIs that cannot exist in a Server Component — so the *first* real thing that page does is
already client work. Fetching session/scenario/persona via TanStack Query inside that same
client boundary, rather than as Server Component props, avoids the SSR-cookie-forwarding
complexity above and costs nothing the architecture wasn't already paying: CLAUDE.md §4's own
TypeScript standard is "Server state -> TanStack Query," and that's exactly what this is.

**What this means concretely:** every page under `/app/*`
(`app/app/(shell)/page.tsx`, `.../sessions/page.tsx`, `.../sessions/[id]/page.tsx`,
`app/app/(bare)/practice/[sessionId]/page.tsx`) is a thin Server Component — route structure and
`params` unwrapping only — that renders one client component doing the actual authenticated
fetching. This is a real deviation from the phase doc's illustrative code fragment, not a literal
non-compliance with anything CLAUDE.md states as a hard rule; it's recorded here per CLAUDE.md
§13 ("if you think a spec decision is wrong, say so once, briefly, with the reason").
