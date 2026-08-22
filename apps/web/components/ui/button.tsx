import { clsx } from "clsx";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors " +
  "disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap";

// The only place `--accent` is used for a background — Task 3.1: "exactly one accent colour,
// used for primary actions only."
const variants: Record<Variant, string> = {
  primary: "bg-[var(--accent)] text-[var(--text-on-accent)] hover:bg-[var(--accent-hover)]",
  secondary:
    "border bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--bg-raised)]",
  ghost: "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-raised)]",
  danger: "bg-[var(--danger)] text-[var(--text-on-accent)] hover:bg-[var(--danger-hover)]",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({ variant = "secondary", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      className={clsx(base, variants[variant], sizes[size], "duration-150", className)}
      {...props}
    />
  );
}
