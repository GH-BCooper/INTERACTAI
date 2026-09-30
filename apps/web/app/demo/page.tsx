import type { Metadata } from "next";

import { ArrowRight } from "lucide-react";

import { DemoReport, type DemoBundle } from "@/components/demo/demo-report";
import { ButtonLink } from "@/components/ui/button";

import bundle from "../../public/demo/sample-session.json";

export const metadata: Metadata = {
  title: "Sample session",
  description: "A recorded practice session and its evidence-linked report. No account, no models running.",
};

/** Phase 6 TASK 6.5 — public, static. The bundle is imported at build time, so this route makes
 * no API, realtime or coach call at all: it works with every backend service stopped. */
export default function DemoPage() {
  return (
    <main className="min-h-dvh pb-24">
      <DemoReport bundle={bundle as unknown as DemoBundle} />
      {/* docs/ui-audit-2026-09.md §2: the demo shouldn't be a dead end. */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-[var(--bg-card)]/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <p className="text-sm">
            <span className="font-medium">Your turn.</span>{" "}
            <span className="hidden text-[var(--text-secondary)] sm:inline">Practise out loud and get your own evidence-linked report.</span>
          </p>
          <ButtonLink href="/signin" variant="primary" size="sm" className="shrink-0">
            Sign in to try it yourself <ArrowRight size={14} aria-hidden />
          </ButtonLink>
        </div>
      </div>
    </main>
  );
}
