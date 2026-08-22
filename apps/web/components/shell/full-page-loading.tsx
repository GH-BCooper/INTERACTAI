export function FullPageLoading() {
  return (
    <div className="flex h-dvh w-full items-center justify-center bg-[var(--bg-page)]">
      <div
        aria-hidden
        className="h-8 w-8 animate-pulse-gentle rounded-full border-2"
        style={{ borderColor: "var(--accent)" }}
      />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
