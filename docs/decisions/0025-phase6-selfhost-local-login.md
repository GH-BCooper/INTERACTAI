# 0025 — Self-host sign-in without OAuth

**Context.** AS-12 requires self-host with zero external API keys. The only sign-in paths were
GitHub and Google OAuth, and each needs an OAuth app, which is an external key.

**Decision.** `GET /auth/local/login`, enabled only by `SELF_HOST_LOCAL_LOGIN=true` and refused
whenever `ENVIRONMENT=production`. It signs the browser into one local account
(`local@selfhost.invalid`) through the same token-fragment and refresh-cookie handoff as OAuth. The
web app shows "Continue locally" only when built with `NEXT_PUBLIC_SELF_HOST=true`. The refresh cookie
is not `Secure` for `ENVIRONMENT=selfhost`, because `http://localhost` has no TLS.

**Consequence.** Anyone who can reach a self-hosted instance is that local user. That is correct on
your own machine and wrong on a network, which is why production refuses it.
