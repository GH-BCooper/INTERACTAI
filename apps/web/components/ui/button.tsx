import { clsx } from "clsx";
import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ComponentProps } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors duration-150 " +
  "disabled:opacity-50 disabled:pointer-events-none aria-disabled:opacity-50 aria-disabled:pointer-events-none whitespace-nowrap";

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
  lg: "h-11 px-5 text-sm",
};

/** The button look, for elements that are not `<button>` — a link that navigates must be a
 * link, never a `<button>` wrapped in an `<a>` (invalid HTML, and a double tab stop). */
export function buttonClasses({
  variant = "secondary",
  size = "md",
  className,
}: { variant?: Variant; size?: Size; className?: string } = {}): string {
  return clsx(base, variants[variant], sizes[size], className);
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({ variant = "secondary", size = "md", className, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={buttonClasses({ variant, size, className })} {...props} />;
}

type ButtonLinkProps = ComponentProps<typeof Link> & { variant?: Variant; size?: Size };

/** An internal navigation styled as a button: one element, one tab stop, client-side routing. */
export function ButtonLink({ variant = "secondary", size = "md", className, ...props }: ButtonLinkProps) {
  return <Link className={buttonClasses({ variant, size, className })} {...props} />;
}

/** An external (or full-page, e.g. OAuth) navigation styled as a button. */
export function ButtonAnchor({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant; size?: Size }) {
  return <a className={buttonClasses({ variant, size, className })} {...props} />;
}
