"use client";

import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/plugins/regions";

import type { TurnOut } from "@/lib/api/types";
import { resolveCssVar } from "@/lib/theme/resolve-css-var";
import { scoreBandVarName } from "@/components/score/score-color";
import { usePlayerStore } from "@/stores/player-store";

const STORE_WRITE_THROTTLE_MS = 100; // Task 3.4a: "throttle store writes to ~10Hz"

export interface UseReportWaveformOptions {
  containerRef: React.RefObject<HTMLDivElement | null>;
  url: string | null;
  peaks: number[] | null;
  durationMs: number | null;
  /** `undefined` while the turns query is still loading — deliberately distinct from `[]` (a
   * session that genuinely has zero turns), so the region-sync effect below can tell "not
   * loaded yet" from "loaded, and empty" and never bakes in a premature empty region set. */
  turns: TurnOut[] | undefined;
  highlightTurnId: string | null;
  lowlightTurnId: string | null;
}

export interface ReportWaveform {
  isReady: boolean;
  isPlaying: boolean;
  playPause: () => void;
  seekToMs: (ms: number) => void;
  jumpToLowlight: () => void;
  jumpToHighlight: () => void;
  setPlaybackRate: (rate: number) => void;
}

/** Task 3.3f/3.4: wavesurfer.js wired to lib/audio's already-established design (real amplitude,
 * never decode audio client-side — the peaks array is precomputed server-side, Task 3.3a) and
 * to the single-source-of-truth player store (Task 3.4a). wavesurfer renders to `<canvas>`, so
 * every colour it needs is resolved from CSS custom properties to a concrete value up front
 * (`var()` is never interpreted by a canvas 2D context) — see lib/theme/resolve-css-var.ts.
 *
 * Two separate effects, deliberately: the instance itself is created/destroyed only when the
 * underlying *audio* identity changes (url/peaks/duration — Task 3.3f: "destroy on unmount,"
 * same principle applied to any actual audio swap); turns/highlight/lowlight are synced into
 * regions independently, whenever they change, so a `turns` query that resolves *after* the
 * `recording` query still ends up with correct region content instead of silently freezing on
 * whatever was available at creation time. */
export function useReportWaveform({
  containerRef,
  url,
  peaks,
  durationMs,
  turns,
  highlightTurnId,
  lowlightTurnId,
}: UseReportWaveformOptions): ReportWaveform {
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const setPlayheadMs = usePlayerStore((s) => s.setPlayheadMs);
  const lastWriteRef = useRef(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || peaks === null || durationMs === null) return;

    const regions = RegionsPlugin.create();
    const ws = WaveSurfer.create({
      container,
      url: url ?? undefined,
      peaks: [peaks],
      duration: durationMs / 1000,
      height: 64,
      waveColor: resolveCssVar("--text-tertiary"),
      progressColor: resolveCssVar("--accent"),
      cursorColor: resolveCssVar("--accent"),
      cursorWidth: 2,
      barWidth: 2,
      barGap: 1,
      barRadius: 1,
      interact: url !== null, // Task 3.4 edge case: no recording -> replay controls disabled
      normalize: false, // peaks are already normalised server-side (0..1 of int16 full scale)
    });
    ws.registerPlugin(regions);
    wsRef.current = ws;
    regionsRef.current = regions;

    ws.on("ready", () => setIsReady(true));
    ws.on("play", () => setIsPlaying(true));
    ws.on("pause", () => setIsPlaying(false));
    ws.on("finish", () => setIsPlaying(false));

    function writePlayhead(currentTimeS: number) {
      const now = performance.now();
      if (now - lastWriteRef.current < STORE_WRITE_THROTTLE_MS) return;
      lastWriteRef.current = now;
      setPlayheadMs(Math.round(currentTimeS * 1000));
    }
    ws.on("timeupdate", writePlayhead);
    ws.on("interaction", (newTimeS) => {
      // A direct user click/drag — always reflect it immediately, never throttled, since this
      // is a discrete one-off event rather than a 60Hz stream.
      lastWriteRef.current = performance.now();
      setPlayheadMs(Math.round(newTimeS * 1000));
    });

    // Task 3.3f: "Destroy the instance on unmount — otherwise an AudioContext leaks per report
    // opened."
    return () => {
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
      setIsReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef, url, peaks, durationMs]);

  useEffect(() => {
    const regions = regionsRef.current;
    if (!regions || !isReady || turns === undefined) return;

    regions.clearRegions();

    const userTurnTint = `color-mix(in srgb, ${resolveCssVar("--accent")} 10%, transparent)`;
    for (const t of turns) {
      regions.addRegion({
        id: `turn-${t.id}`,
        start: t.start_ms / 1000,
        end: t.end_ms / 1000,
        drag: false,
        resize: false,
        color: t.speaker === "user" ? userTurnTint : "transparent",
      });
    }

    if (highlightTurnId) {
      const t = turns.find((x) => x.id === highlightTurnId);
      if (t) {
        regions.addRegion({
          id: "marker-highlight",
          start: t.start_ms / 1000,
          end: t.start_ms / 1000,
          content: "Highlight",
          color: resolveCssVar(scoreBandVarName("strong")),
          drag: false,
          resize: false,
        });
      }
    }
    if (lowlightTurnId) {
      const t = turns.find((x) => x.id === lowlightTurnId);
      if (t) {
        regions.addRegion({
          id: "marker-lowlight",
          start: t.start_ms / 1000,
          end: t.start_ms / 1000,
          content: "Lowlight",
          color: resolveCssVar(scoreBandVarName("weak")),
          drag: false,
          resize: false,
        });
      }
    }
    // isReady flips true only once per instance lifetime (reset on teardown above), so this
    // still re-fires correctly on turns/highlight/lowlight changes without depending on `regions`
    // itself, which is a stable ref value across renders.
  }, [isReady, turns, highlightTurnId, lowlightTurnId]);

  return {
    isReady,
    isPlaying,
    playPause: () => void wsRef.current?.playPause(),
    seekToMs: (ms: number) => wsRef.current?.setTime(ms / 1000),
    jumpToLowlight: () => {
      const t = turns?.find((x) => x.id === lowlightTurnId);
      if (t) wsRef.current?.setTime(t.start_ms / 1000);
    },
    jumpToHighlight: () => {
      const t = turns?.find((x) => x.id === highlightTurnId);
      if (t) wsRef.current?.setTime(t.start_ms / 1000);
    },
    setPlaybackRate: (rate: number) => wsRef.current?.setPlaybackRate(rate),
  };
}
