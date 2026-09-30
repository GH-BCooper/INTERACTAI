"use client";

import { ErrorState } from "@/components/ui/error-state";

/** CLAUDE.md §6: "never a stack trace" — the root boundary for public pages. */
export default function RootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState error={error} reset={reset} homeHref="/" homeLabel="Back to home" fullPage />;
}
