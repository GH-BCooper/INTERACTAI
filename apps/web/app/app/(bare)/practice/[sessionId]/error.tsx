"use client";

import { ErrorState } from "@/components/ui/error-state";

/** The practice room's own boundary. The recording is uploaded incrementally by realtime, so a
 * client-side crash here never loses what was already said — the recovery says so. */
export default function PracticeError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState error={error} reset={reset} homeHref="/app/sessions" homeLabel="Go to session history" fullPage />;
}
