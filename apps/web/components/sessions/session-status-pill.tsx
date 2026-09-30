import { Pill } from "@/components/ui/primitives";
import type { SessionListItemOut } from "@/lib/api/types";

/** One human word for where a session is — never the raw uppercase enum. */
export function SessionStatusPill({ session }: { session: Pick<SessionListItemOut, "status" | "report_status"> }) {
  if (session.status === "failed") return <Pill tone="bad">Didn&apos;t complete</Pill>;
  if (session.status === "created" || session.status === "active") return <Pill tone="accent">In progress</Pill>;
  if (session.status === "closing" || session.report_status === "pending" || session.report_status === null) {
    return <Pill>Scoring…</Pill>;
  }
  if (session.report_status === "failed") return <Pill tone="bad">Report failed</Pill>;
  return <Pill tone="neutral">Completed</Pill>;
}
