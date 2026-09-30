"use client";

import { ErrorState } from "@/components/ui/error-state";

/** The authenticated app's boundary (docs/ui-audit-2026-09.md §1.1). */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState error={error} reset={reset} />;
}
