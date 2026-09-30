"use client";

import { Check } from "lucide-react";
import { useEffect, useState } from "react";

/** One saving/saved/failed indicator for every settings form. "Saved" fades after a few seconds
 * so it confirms the last action without lingering as stale state. */
export function SaveStatus({ pending, savedAt, error }: { pending: boolean; savedAt: number | null; error?: string | null }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (savedAt === null) return;
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), 3000);
    return () => clearTimeout(timer);
  }, [savedAt]);

  if (pending) return <span role="status" className="text-xs text-[var(--text-tertiary)]">Saving…</span>;
  if (error) return <span role="alert" className="text-xs text-[var(--status-bad)]">{error}</span>;
  if (visible)
    return (
      <span role="status" className="inline-flex items-center gap-1 text-xs text-[var(--status-ok)] animate-fade-in">
        <Check size={12} aria-hidden /> Saved
      </span>
    );
  return null;
}
