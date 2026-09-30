import { AlertCircle, ArrowLeft, Github, Laptop } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { RedirectIfAuthenticated } from "@/components/shell/redirect-if-authenticated";
import { ButtonAnchor } from "@/components/ui/button";
import { Wordmark } from "@/components/ui/logo";
import { API_BASE_URL } from "@/lib/api/client";

export const metadata: Metadata = { title: "Sign in" };

const SELF_HOST = process.env.NEXT_PUBLIC_SELF_HOST === "true";

// `?error=` codes set by services/api's OAuth callback (routers/auth.py) and /auth/callback.
const ERROR_MESSAGES: Record<string, { title: string; body: string }> = {
  access_denied: {
    title: "Sign-in was cancelled",
    body: "You declined access at the provider. Choose a provider below to try again.",
  },
  state_expired: {
    title: "That sign-in link expired",
    body: "Sign-in has to finish within a few minutes, and each link works once. Start again below.",
  },
  provider_error: {
    title: "The provider didn't complete sign-in",
    body: "GitHub or Google returned an error. Try again, or use the other provider.",
  },
  callback_failed: {
    title: "Sign-in didn't complete",
    body: "We couldn't read the sign-in response. Try again below.",
  },
};

/** Monochrome Google "G" (lucide ships no brand marks). currentColor, so it follows the theme. */
function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden fill="currentColor">
      <path d="M21.35 11.1H12v2.98h5.35c-.23 1.4-1.66 4.1-5.35 4.1-3.22 0-5.85-2.67-5.85-5.96S8.78 6.26 12 6.26c1.83 0 3.06.78 3.76 1.45l2.57-2.47C16.68 3.7 14.55 2.75 12 2.75 6.89 2.75 2.75 6.89 2.75 12s4.14 9.25 9.25 9.25c5.34 0 8.88-3.75 8.88-9.04 0-.61-.07-1.07-.15-1.53z" />
    </svg>
  );
}

/** Public — no AuthGate above this. A signed-in visitor who lands here is sent on to /app by
 * the client bootstrap check below rather than by a server redirect, since "signed in" is only
 * knowable once the httpOnly refresh cookie has actually been exchanged. Moved from `/` in
 * Phase 6, when `/` became the public landing page (TASK 6.6). */
export default async function SignInPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  const errorMessage = error ? (ERROR_MESSAGES[error] ?? ERROR_MESSAGES.callback_failed) : null;

  return (
    <main className="grid min-h-dvh md:grid-cols-2">
      <RedirectIfAuthenticated />

      {/* Brand panel — hidden on small screens, where the form is the whole page. */}
      <section className="hidden flex-col justify-between border-r bg-[var(--bg-card)] p-10 md:flex">
        <Link href="/" aria-label="InteractAI home">
          <Wordmark />
        </Link>
        <div className="max-w-sm">
          <p className="text-lg font-medium">Speak. Be answered convincingly and fast. Be scored defensibly.</p>
          <ul className="mt-6 flex flex-col gap-3 text-sm text-[var(--text-secondary)]">
            <li>An interviewer that replies out loud, in character.</li>
            <li>Every score linked to the exact words you said.</li>
            <li>Your audio, your choice: delete it any time.</li>
          </ul>
        </div>
        <p className="text-xs text-[var(--text-tertiary)]">Measures performance against a rubric. Does not predict hiring outcomes.</p>
      </section>

      <section className="flex flex-col px-6 py-6">
        <Link
          href="/"
          className="inline-flex w-fit items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <ArrowLeft size={14} aria-hidden /> Back to home
        </Link>

        <div className="mx-auto flex w-full max-w-xs flex-1 flex-col justify-center py-10 animate-rise-in">
          <Wordmark className="mb-8 md:hidden" />
          <h1 className="text-lg font-medium">Sign in</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">New here? The same button creates your account.</p>

          {errorMessage && (
            <div role="alert" className="mt-5 flex gap-2 rounded-lg border border-[var(--status-bad)] p-3 text-sm">
              <AlertCircle size={16} aria-hidden className="mt-0.5 shrink-0 text-[var(--status-bad)]" />
              <div>
                <p className="font-medium">{errorMessage.title}</p>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{errorMessage.body}</p>
              </div>
            </div>
          )}

          <div className="mt-6 flex flex-col gap-3">
            {SELF_HOST && (
              // Phase 6 TASK 6.4d: self-host runs with zero OAuth apps configured.
              <ButtonAnchor href={`${API_BASE_URL}/auth/local/login`} variant="primary" size="lg">
                <Laptop size={16} aria-hidden /> Continue locally
              </ButtonAnchor>
            )}
            {/* Equal weight: neither provider is "the" recommended one. */}
            <ButtonAnchor href={`${API_BASE_URL}/auth/github/login`} variant="secondary" size="lg">
              <Github size={16} aria-hidden /> Continue with GitHub
            </ButtonAnchor>
            <ButtonAnchor href={`${API_BASE_URL}/auth/google/login`} variant="secondary" size="lg">
              <GoogleMark /> Continue with Google
            </ButtonAnchor>
          </div>

          <p className="mt-6 text-xs leading-relaxed text-[var(--text-tertiary)]">
            By continuing you agree to the{" "}
            <Link href="/terms" className="underline hover:text-[var(--text-primary)]">
              terms
            </Link>{" "}
            and{" "}
            <Link href="/privacy" className="underline hover:text-[var(--text-primary)]">
              privacy notice
            </Link>
            . Training use of your sessions is a separate, opt-in choice.
          </p>
        </div>
      </section>
    </main>
  );
}
