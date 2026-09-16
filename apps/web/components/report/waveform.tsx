"use client";

import { ChevronLeft, ChevronRight, Pause, Play, TrendingDown } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import type { ReportWaveform } from "@/hooks/use-report-waveform";
import type { TurnOut } from "@/lib/api/types";
import { usePlayerStore } from "@/stores/player-store";

interface WaveformProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  waveform: ReportWaveform;
  url: string | null;
  peaks: number[] | null;
  durationMs: number | null;
  turns: TurnOut[];
  lowlightTurnId: string | null;
}

/** Task 3.3f/3.4c. `useReportWaveform` (the wavesurfer.js instance itself) is owned by the
 * parent report-view.tsx — Task 3.4a's "one source of truth" means the same instance has to be
 * reachable from the transcript and verdict block's click-to-seek handlers too, not private to
 * this component. This is the presentational half: the container div wavesurfer renders into,
 * plus the play/prev/next/lowlight/speed controls. */
export function Waveform({ containerRef, waveform, url, peaks, durationMs, turns, lowlightTurnId }: WaveformProps) {
  const playheadMs = usePlayerStore((s) => s.playheadMs);
  const sortedTurns = useMemo(() => [...turns].sort((a, b) => a.start_ms - b.start_ms), [turns]);

  function seekRelative(direction: 1 | -1) {
    const idx = sortedTurns.findIndex((t) => playheadMs >= t.start_ms && playheadMs < t.end_ms);
    const targetIdx = idx === -1 ? (direction === 1 ? 0 : sortedTurns.length - 1) : idx + direction;
    const target = sortedTurns[targetIdx];
    if (target) waveform.seekToMs(target.start_ms);
  }

  if (peaks === null || durationMs === null) {
    return (
      <div className="flex h-16 items-center justify-center rounded-md border border-dashed text-xs text-[var(--text-tertiary)]">
        No recording was captured for this session.
      </div>
    );
  }

  return (
    <div>
      {/* Reserves wavesurfer's 64px canvas height up front so mounting it causes no layout shift. */}
      <div ref={containerRef} className="min-h-16 w-full" />
      {url === null && (
        <p className="mt-2 text-xs text-[var(--text-tertiary)]">
          The recording has expired — the transcript and scores below are unaffected.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-1">
        <Button variant="secondary" size="sm" onClick={() => seekRelative(-1)} disabled={url === null} aria-label="Previous turn">
          <ChevronLeft size={14} />
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={waveform.playPause}
          disabled={url === null || !waveform.isReady}
          aria-label={waveform.isPlaying ? "Pause" : "Play"}
        >
          {waveform.isPlaying ? <Pause size={14} /> : <Play size={14} />}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => seekRelative(1)} disabled={url === null} aria-label="Next turn">
          <ChevronRight size={14} />
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={waveform.jumpToLowlight}
          disabled={url === null || !lowlightTurnId}
        >
          <TrendingDown size={14} className="mr-1" /> Jump to lowlight
        </Button>
        <Button variant="ghost" size="sm" onClick={() => waveform.setPlaybackRate(1.5)} disabled={url === null}>
          1.5×
        </Button>
      </div>
    </div>
  );
}
