import type { Metadata } from "next";

import { DemoReport, type DemoBundle } from "@/components/demo/demo-report";

import bundle from "../../public/demo/sample-session.json";

export const metadata: Metadata = {
  title: "Sample session · InteractAI",
  description: "A recorded practice session and its evidence-linked report. No account, no models running.",
};

/** Phase 6 TASK 6.5 — public, static. The bundle is imported at build time, so this route makes
 * no API, realtime or coach call at all: it works with every backend service stopped. */
export default function DemoPage() {
  return (
    <main className="min-h-dvh">
      <DemoReport bundle={bundle as unknown as DemoBundle} />
    </main>
  );
}
