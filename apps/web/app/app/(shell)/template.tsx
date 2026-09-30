import type { ReactNode } from "react";

/** docs/ui-audit-2026-09.md §1.13 — a template (unlike a layout) remounts on every navigation,
 * so each route's content gets one subtle 150ms fade-in. The shell around it never moves. */
export default function ShellTemplate({ children }: { children: ReactNode }) {
  return <div className="animate-fade-in">{children}</div>;
}
