"use client";

import { clsx } from "clsx";
import { useRef, type KeyboardEvent } from "react";

export interface SegmentOption<T extends string | number> {
  value: T;
  label: string;
}

/** docs/ui-audit-2026-09.md §1.8 — one control for "pick one of a few": the library filters,
 * the start dialog's difficulty and duration, the progress family tabs. A radio group, so arrow
 * keys move the selection and screen readers announce "2 of 4". `variant="pills"` wraps onto
 * several lines (filters); `"segmented"` is one joined bar (a form value). */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
  variant = "pills",
  size = "sm",
  className,
}: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  variant?: "pills" | "segmented";
  size?: "sm" | "md";
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const delta = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (delta === 0) return;
    e.preventDefault();
    const next = (index + delta + options.length) % options.length;
    const option = options[next];
    if (!option) return;
    onChange(option.value);
    refs.current[next]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={clsx(
        variant === "pills" ? "flex flex-wrap gap-2" : "grid auto-cols-fr grid-flow-col rounded-md border bg-[var(--bg-page)] p-0.5",
        className,
      )}
    >
      {options.map((o, i) => {
        const selected = o.value === value;
        return (
          <button
            key={String(o.value)}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={clsx(
              "whitespace-nowrap transition-colors duration-150",
              size === "sm" ? "text-xs" : "text-sm",
              variant === "pills"
                ? clsx(
                    "rounded-full border px-3 py-1",
                    selected
                      ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--text-on-accent)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]",
                  )
                : clsx(
                    "rounded px-3",
                    size === "sm" ? "h-7" : "h-9",
                    selected
                      ? "bg-[var(--bg-raised)] font-medium text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                  ),
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
