import type { ReactNode } from "react";

import { AuthGate } from "@/components/shell/auth-gate";

// A top-level route (`/onboarding`, not `/app/onboarding`, per docs/phase-4-BUILD.md TASK
// 4.3) — authenticated like everything under /app, but deliberately outside app/app/(shell)
// or app/app/(bare): onboarding is neither the persistent-chrome app shell nor the practice
// room, it's its own bare, focused surface.
export default function OnboardingLayout({ children }: { children: ReactNode }) {
  return <AuthGate>{children}</AuthGate>;
}
