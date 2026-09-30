import { clsx } from "clsx";
import type { ReactNode } from "react";

/** An on/off setting. A real checkbox underneath (keyboard, forms, screen readers all work
 * unchanged); the track and thumb are just its styling, and `role="switch"` announces it as one. */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
  id,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <label className={clsx("flex items-start justify-between gap-4", disabled ? "opacity-50" : "cursor-pointer")}>
      <span className="text-sm">
        {label}
        {description && <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">{description}</span>}
      </span>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input
          id={id}
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="peer sr-only"
        />
        <span
          aria-hidden
          className="h-5 w-9 rounded-full border bg-[var(--bg-raised)] transition-colors duration-150 peer-checked:border-[var(--accent)] peer-checked:bg-[var(--accent)] peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-[var(--focus-ring)]"
        />
        <span
          aria-hidden
          className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-[var(--text-secondary)] transition-transform duration-150 [transition-timing-function:var(--motion-ease)] peer-checked:translate-x-4 peer-checked:bg-[var(--text-on-accent)]"
        />
      </span>
    </label>
  );
}

/** A plain checkbox with a label — for choices that are agreements, not settings (consent). */
export function Checkbox({
  checked,
  onChange,
  children,
  className,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={clsx("flex cursor-pointer items-start gap-3 text-sm", className)}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent)]"
      />
      <span>{children}</span>
    </label>
  );
}
