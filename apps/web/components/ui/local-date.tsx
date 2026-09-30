/**
 * A date rendered in the *viewer's* locale and timezone, without a hydration mismatch.
 *
 * `new Date(x).toLocaleDateString()` inside a client component is only safe when the data arrives
 * client-side, which is true for every `/app/*` page (TanStack Query, nothing to render on the
 * server). It is not true for `/demo`, which imports its bundle at build time and therefore
 * server-renders the report: Node formatted the date in the server's locale and timezone, the
 * browser formatted it in the viewer's, the two strings differed, and React threw
 * "server rendered text didn't match the client" and discarded the whole tree to re-render it.
 * That was firing on the one page the project shares publicly with no account needed.
 *
 * Formatting the date in UTC would agree across both but would show the wrong day to anyone whose
 * local date differs from UTC's — the opposite bug, and a quieter one. So the server's rendering
 * is treated as a placeholder that the client is expected to correct: `suppressHydrationWarning`
 * tells React that this one text node is legitimately environment-dependent, and the viewer's
 * locale wins after hydration. The machine-readable value goes in `dateTime` either way.
 *
 * `relative` renders "2 days ago" (lists), with the absolute date in the tooltip.
 */
export function LocalDate({
  value,
  withTime = false,
  relative = false,
  options,
}: {
  value: string;
  withTime?: boolean;
  relative?: boolean;
  options?: Intl.DateTimeFormatOptions;
}) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <>—</>;
  const absolute = options
    ? date.toLocaleDateString(undefined, options)
    : withTime
      ? date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
      : date.toLocaleDateString(undefined, { dateStyle: "medium" });
  const text = relative ? formatRelative(date, new Date()) : absolute;
  return (
    <time dateTime={date.toISOString()} title={relative ? absolute : undefined} suppressHydrationWarning>
      {text}
    </time>
  );
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

export function formatRelative(date: Date, now: Date): string {
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 60) return "just now";
  const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (abs >= size) return fmt.format(Math.round(seconds / size), unit);
  }
  return "just now";
}
