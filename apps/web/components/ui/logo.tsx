import { clsx } from "clsx";

/** The mark: a persona ring (the practice room's presence circle) with a speech wave through it.
 * Accent for the ring, currentColor for the wave, so it works on either theme. */
export function LogoMark({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <circle cx="12" cy="12" r="10" stroke="var(--accent)" strokeWidth="2" />
      <path
        d="M6.5 12h1.5l1.5-3.5 2 7 2-9 2 7.5 1.5-2h1"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Wordmark({ className, size = 20 }: { className?: string; size?: number }) {
  return (
    <span className={clsx("inline-flex items-center gap-2 font-medium tracking-tight", className)}>
      <LogoMark size={size} />
      <span>InteractAI</span>
    </span>
  );
}
