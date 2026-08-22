# 0013 — The OAuth callback redirects to the SPA instead of returning JSON

**Phase:** 3, Task 3.1 (the app shell needs a real sign-in flow).

## The gap

Phase 0's `GET /auth/{provider}/callback` (`services/api/app/routers/auth.py`) returned
`TokenResponse` — a JSON body — directly. That's what the *OAuth provider's own redirect*
lands the browser on: a top-level navigation, not a `fetch()` call the frontend could ever
intercept. A browser hitting this endpoint the way the flow actually works would be stranded on
a bare JSON page at `localhost:8000`, with no route back to the app and no way for
`apps/web` to ever see the access token. Nothing in Phase 0's own acceptance criteria caught this
because the OAuth round trip itself was explicitly out of scope for automated testing
("needs a human + a real browser") — this seam was invisible until Phase 3 built the login
button that actually has to complete the flow.

## The fix

`callback()` now returns a `307` redirect to
`{WEB_ORIGIN}/auth/callback#token={access_token}&expires_in={n}`, with the refresh token still
set as the same httpOnly cookie as before (a `Set-Cookie` header survives the response type
change untouched).

**The access token travels in the URL fragment, not a query string.** A fragment is never sent
to any server — not this one on a later request, not an analytics beacon, not a proxy access
log — which matters for a value that is bearer-equivalent for its 15-minute lifetime.
`apps/web/app/auth/callback/page.tsx` reads it via `window.location.hash` and stores it in
memory (`stores/auth-store.ts`), then redirects to `/app`.

## What this doesn't change

The refresh-token cookie, its `httponly`/`samesite=lax`/`path=/auth` attributes, and the
rotation/reuse-detection logic in `core/security.py` are all exactly as Phase 0 built them —
this decision only changes what the *response body* is, not the auth model itself.
