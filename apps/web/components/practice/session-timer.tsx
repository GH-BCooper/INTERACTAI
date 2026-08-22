function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function SessionTimer({
  elapsedMs,
  targetMinutes,
}: {
  elapsedMs: number;
  targetMinutes: number;
}) {
  const remainingMs = Math.max(0, targetMinutes * 60_000 - elapsedMs);
  return (
    <div className="font-mono text-xs text-[var(--text-tertiary)]">
      {formatDuration(elapsedMs)} elapsed · {formatDuration(remainingMs)} remaining
    </div>
  );
}
