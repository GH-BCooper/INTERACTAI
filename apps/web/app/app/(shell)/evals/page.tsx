import type { Metadata } from "next";

import { EvalsDashboard } from "@/components/evals/evals-dashboard";

export const metadata: Metadata = { title: "Evaluations" };

/** Phase 6 TASK 6.2 — admin only; every query behind it is AdminUser-gated server-side. */
export default function EvalsPage() {
  return <EvalsDashboard />;
}
