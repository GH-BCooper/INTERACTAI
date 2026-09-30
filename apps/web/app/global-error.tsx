"use client";

import { ErrorState } from "@/components/ui/error-state";

import "./globals.css";

/** Catches a throw in the root layout itself, so it has to render its own <html>/<body>. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <ErrorState error={error} reset={reset} homeHref="/" homeLabel="Back to home" fullPage />
      </body>
    </html>
  );
}
