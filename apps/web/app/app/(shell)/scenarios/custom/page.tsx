import { Wand2 } from "lucide-react";
import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Custom scenario" };

// Task 4.2: authoring is P1 and not built (POST /scenarios returns 501). The library no longer
// links here (docs/ui-audit-2026-09.md §6); this stays only so an old bookmark gets an honest
// page instead of a 404.
export default function CustomScenarioComingSoonPage() {
  return (
    <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <EmptyState
        icon={<Wand2 size={18} />}
        title="Custom scenarios aren't available yet"
        body="Authoring your own brief, persona and rubric isn't built. For now, pick the closest scenario in the library and set the difficulty when you start."
        action={
          <ButtonLink href="/app/scenarios" variant="primary" size="sm">
            Back to the library
          </ButtonLink>
        }
      />
    </div>
  );
}
