import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

/** docs/ui-audit-2026-09.md §1.8 — one look for every text control. `bg-card` everywhere (the
 * audit found selects on `bg-page` in one dialog and `bg-card` in the next). */
const control =
  "w-full rounded-md border bg-[var(--bg-card)] text-sm text-[var(--text-primary)] transition-colors duration-150 " +
  "placeholder:text-[var(--text-tertiary)] hover:border-[var(--text-tertiary)] disabled:opacity-50";

export function Label({ htmlFor, children, className }: { htmlFor?: string; children: ReactNode; className?: string }) {
  return (
    <label htmlFor={htmlFor} className={clsx("block text-xs text-[var(--text-secondary)]", className)}>
      {children}
    </label>
  );
}

export function FieldHint({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={clsx("mt-1 text-xs text-[var(--text-tertiary)]", className)}>{children}</p>;
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx(control, "h-10 px-3", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx(control, "px-3 py-2 leading-relaxed", className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={clsx("relative", className)}>
      <select className={clsx(control, "h-10 appearance-none pl-3 pr-9")} {...props}>
        {children}
      </select>
      <ChevronDown
        size={14}
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]"
      />
    </div>
  );
}
