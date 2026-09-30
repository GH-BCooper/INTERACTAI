"use client";

import { clsx } from "clsx";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useEffect } from "react";

import { useToastStore, type Toast } from "@/stores/toast-store";

const AUTO_DISMISS_MS = 6000;

const VARIANT_ICON = {
  info: Info,
  success: CheckCircle2,
  error: AlertCircle,
} as const;

// Status colours, never --score-* (a toast is never a rubric judgement).
const VARIANT_ICON_CLASS = {
  info: "text-[var(--accent)]",
  success: "text-[var(--status-ok)]",
  error: "text-[var(--status-bad)]",
} as const;

function ToastCard({ id, title, description, action, variant = "info" }: Toast) {
  const dismiss = useToastStore((s) => s.dismiss);
  const Icon = VARIANT_ICON[variant];

  useEffect(() => {
    const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [id, dismiss]);

  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className="flex w-80 max-w-[calc(100vw-2rem)] items-start gap-3 rounded-lg border bg-[var(--bg-raised)] p-4 text-[var(--text-primary)] animate-toast-in"
    >
      <Icon size={16} aria-hidden className={clsx("mt-0.5 shrink-0", VARIANT_ICON_CLASS[variant])} />
      <div className="min-w-0 flex-1">
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
      className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2"
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastCard {...t} />
        </div>
      ))}
    </div>
  );
}
