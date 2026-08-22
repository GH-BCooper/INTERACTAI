import { forwardRef } from "react";

/** Task 3.2 non-negotiable #1: "Microphone level meter visible at all times... must not go
 * through React state — write to a ref/CSS custom property." The forwarded ref is written to
 * directly by hooks/use-audio-capture.ts on every worklet meter message (>= 20Hz); this
 * component itself never re-renders because of it — the `--level` custom property and the
 * `transform` that reads it both live on the same DOM node, so the browser updates the bar
 * without React ever being involved. */
export const MicLevelMeter = forwardRef<HTMLDivElement>(function MicLevelMeter(_props, ref) {
  return (
    <div className="flex w-28 items-center gap-2" role="presentation">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-raised)]">
        <div
          ref={ref}
          className="h-full origin-left rounded-full bg-[var(--accent)]"
          style={{ transform: "scaleX(min(1, calc(var(--level, 0) * 5)))" }}
        />
      </div>
    </div>
  );
});
