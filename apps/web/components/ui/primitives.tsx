import { clsx } from "clsx";
import type { HTMLAttributes, ReactNode } from "react";

/** docs/ui-audit-2026-09.md §1.8 — the small presentational primitives every page was
 * restyling by hand: Card, Pill, Skeleton, EmptyState, PageHeader. */

export function Card({ className, interactive = false, ...props }: HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={clsx(
        "rounded-lg border bg-[var(--bg-card)]",
        interactive && "transition-colors duration-150 hover:bg-[var(--bg-raised)]",
        className,
      )}
      {...props}
    />
  );
}

type PillTone = "neutral" | "accent" | "ok" | "bad" | "outline";

const PILL_TONES: Record<PillTone, string> = {
  neutral: "border-transparent bg-[var(--bg-raised)] text-[var(--text-secondary)]",
  accent: "border-[var(--accent)] text-[var(--accent)]",
  // Status, never rubric judgement — see globals.css on why --status-* exists at all.
  ok: "border-[var(--status-ok)] text-[var(--status-ok)]",
  bad: "border-[var(--status-bad)] text-[var(--status-bad)]",
  outline: "border-dashed text-[var(--text-tertiary)]",
};

export function Pill({ tone = "neutral", className, children }: { tone?: PillTone; className?: string; children: ReactNode }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs",
        PILL_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("animate-pulse rounded-md bg-[var(--bg-raised)]", className)} />;
}

export function EmptyState({
  icon,
  title,
  body,
  action,
  className,
  compact = false,
}: {
  icon?: ReactNode;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={clsx(
        "flex flex-col items-center rounded-lg border border-dashed text-center",
        compact ? "gap-2 px-6 py-8" : "gap-3 px-6 py-14",
        className,
      )}
    >
      {icon && (
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-raised)] text-[var(--text-secondary)]">
          {icon}
        </div>
      )}
      <p className="text-md font-medium">{title}</p>
      {body && <div className="max-w-sm text-sm text-[var(--text-secondary)]">{body}</div>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div>
        <h1 className="text-lg font-medium">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-[var(--text-secondary)]">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** "gentle / standard / hard" as a three-step meter plus the capitalised word — never colour
 * alone, and never a --score-* colour (difficulty is not a rubric value). */
export function DifficultyMeter({ difficulty }: { difficulty: string }) {
  const level = difficulty === "hard" ? 3 : difficulty === "standard" ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
      <span aria-hidden className="flex items-end gap-0.5">
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            className={clsx("w-1 rounded-sm", n <= level ? "bg-[var(--text-secondary)]" : "bg-[var(--border)]")}
            style={{ height: `${4 + n * 3}px` }}
          />
        ))}
      </span>
      {capitalize(difficulty)}
    </span>
  );
}

export function capitalize(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ") : value;
}
