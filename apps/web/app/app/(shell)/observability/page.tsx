import type { Metadata } from "next";

import { ObservabilityDashboard } from "@/components/observability/observability-dashboard";

export const metadata: Metadata = { title: "Observability" };

/** Phase 6 TASK 6.1 — admin only; every query behind it is AdminUser-gated server-side. */
export default function ObservabilityPage() {
  return <ObservabilityDashboard />;
}
