import { Compass } from "lucide-react";
import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/button";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-raised)] text-[var(--text-secondary)]">
        <Compass size={18} aria-hidden />
      </div>
      <h1 className="text-md font-medium">There&apos;s nothing at this address</h1>
      <p className="max-w-sm text-sm text-[var(--text-secondary)]">
        The link may be old, or the page may have moved. Nothing you saved is affected.
      </p>
      <div className="mt-2 flex gap-2">
        <ButtonLink href="/app" variant="primary" size="sm">
          Go to your dashboard
        </ButtonLink>
        <ButtonLink href="/" variant="secondary" size="sm">
          Home
        </ButtonLink>
      </div>
    </main>
  );
}
