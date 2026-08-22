export function CaptionLine({ text, enabled }: { text: string; enabled: boolean }) {
  if (!enabled) return null;
  return (
    <p className="min-h-[2.8em] max-w-lg px-4 text-center text-sm leading-relaxed text-[var(--text-secondary)]">
      {text || " "}
    </p>
  );
}
