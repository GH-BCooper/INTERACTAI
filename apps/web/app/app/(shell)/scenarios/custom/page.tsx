import { Button } from "@/components/ui/button";

// Task 4.2: "A prominent Custom scenario entry sits at the end of the grid... the card renders
// and links to a 'coming soon' state; do not build the authoring flow." P1 — deliberately not
// built out further here.
export default function CustomScenarioComingSoonPage() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
      <h1 className="text-lg font-medium">Custom scenarios are coming soon</h1>
      <p className="text-sm text-[var(--text-secondary)]">
        Authoring your own scenario — a custom brief, persona and rubric — isn&apos;t built yet.
        For now, pick the closest scenario from the library and adjust the difficulty and focus
        areas when you start.
      </p>
      <a href="/app/scenarios">
        <Button variant="primary" size="sm" className="mt-2">
          Back to the library
        </Button>
      </a>
    </div>
  );
}
