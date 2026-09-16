import { RedirectIfAuthenticated } from "@/components/shell/redirect-if-authenticated";
import { API_BASE_URL } from "@/lib/api/client";

/** Public — no AuthGate above this. A signed-in visitor who lands here is sent on to /app by
 * the client bootstrap check below rather than by a server redirect, since "signed in" is only
 * knowable once the httpOnly refresh cookie has actually been exchanged. Moved from `/` in
 * Phase 6, when `/` became the public landing page (TASK 6.6). */
const SELF_HOST = process.env.NEXT_PUBLIC_SELF_HOST === "true";
export default function SignInPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-10 px-6 text-center">
      <RedirectIfAuthenticated />
      <div className="max-w-md">
        <h1 className="text-lg font-medium">InteractAI</h1>
        <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
          Speak. Be answered convincingly and fast. Be scored defensibly.
        </p>
      </div>
      <div className="flex w-full max-w-xs flex-col gap-3">
        {SELF_HOST && (
          // Phase 6 TASK 6.4d: self-host runs with zero OAuth apps configured.
          <a
            href={`${API_BASE_URL}/auth/local/login`}
            className="inline-flex h-10 items-center justify-center rounded-md bg-[var(--accent)] text-sm font-medium text-[var(--text-on-accent)] transition-colors hover:bg-[var(--accent-hover)]"
          >
            Continue locally
          </a>
        )}
        <a
          href={`${API_BASE_URL}/auth/github/login`}
          className="inline-flex h-10 items-center justify-center rounded-md bg-[var(--accent)] text-sm font-medium text-[var(--text-on-accent)] transition-colors hover:bg-[var(--accent-hover)]"
        >
          Continue with GitHub
        </a>
        <a
          href={`${API_BASE_URL}/auth/google/login`}
          className="inline-flex h-10 items-center justify-center rounded-md border bg-[var(--bg-card)] text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-raised)]"
        >
          Continue with Google
        </a>
      </div>
    </main>
  );
}
