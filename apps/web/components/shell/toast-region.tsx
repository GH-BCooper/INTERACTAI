"use client";

import { X } from "lucide-react";
import { useEffect } from "react";

import { useToastStore } from "@/stores/toast-store";

const AUTO_DISMISS_MS = 6000;

function ToastCard({
  id,
  title,
  description,
  action,
}: {
  id: string;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  const dismiss = useToastStore((s) => s.dismiss);

  useEffect(() => {
    const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [id, dismiss]);

  return (
    <div
      role="status"
      className="flex w-80 items-start gap-3 rounded-lg border bg-[var(--bg-raised)] p-4 text-[var(--text-primary)] shadow-none"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="flex-1">
        <p className="text-sm font-medium">{title}</p>
        {description && <p className="mt-1 text-xs text-[var(--text-secondary)]">{description}</p>}
        {action && (
          <button
            type="button"
            onClick={() => {
              action.onClick();
              dismiss(id);
            }}
            className="mt-2 text-xs font-medium text-[var(--accent)] hover:text-[var(--accent-hover)]"
          >
            {action.label}
          </button>
        )}
      </div>
      <button
        type="button"
        aria-label="Dismiss notification"
        onClick={() => dismiss(id)}
        className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
      >
        <X size={16} />
      </button>
    </div>
  );
}

/** Task 3.1: bottom-right toast region, an ARIA live region so a screen reader announces
 * "your report is ready" without the user needing to be looking at that corner. */
export function ToastRegion() {
  const toasts = useToastStore((s) => s.toasts);

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastCard {...t} />
        </div>
      ))}
    </div>
  );
}
