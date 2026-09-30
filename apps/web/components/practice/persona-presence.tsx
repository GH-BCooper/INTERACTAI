"use client";

import { clsx } from "clsx";
import { Briefcase, Handshake, MessagesSquare, ScanSearch, UserRound, type LucideIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";
import type { ClientState } from "@/lib/ws-types";

interface PersonaPresenceProps {
  personaName: string;
  /** content/personas/*.yaml `archetype` — picks the persona's glyph. */
  archetype?: string | null;
  clientState: ClientState;
  getAmplitude: () => number;
  /** 0..1 of the session's target length — drawn as a thin arc around the ring. */
  progress?: number;
}

const STATE_LABEL: Record<ClientState, string> = {
  your_turn: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  connection_trouble: "Reconnecting",
  ended: "Session ended",
};

// docs/ui-audit-2026-09.md §7: one distinct glyph per persona archetype instead of an initial.
// The tokens allow no gradients, so identity comes from shape, not colour.
const ARCHETYPE_GLYPH: Record<string, LucideIcon> = {
  interviewer: MessagesSquare,
  hiring_manager: Briefcase,
  recruiter: Handshake,
  skeptic: ScanSearch,
};

const ARC_SIZE = 224; // px, just outside the sm:h-48 ring
const ARC_RADIUS = 108;
const ARC_CIRCUMFERENCE = 2 * Math.PI * ARC_RADIUS;

/** Task 3.2: "One large circular element with the persona's name and an amplitude-reactive
 * ring" — listening pulses gently (CSS animation), thinking gets its own restrained animation
 * (never a spinner — docs/phase-3-LEARN.md §2: "a spinner says the software is loading"), and
 * speaking is driven by *real* playback amplitude, sampled every frame and written straight to
 * a CSS custom property on the ring element — never through React state (same discipline as
 * the mic meter). The state is also always written out under the name: motion alone is not an
 * accessible state signal (docs/ui-audit-2026-09.md §7). */
export function PersonaPresence({ personaName, archetype, clientState, getAmplitude, progress }: PersonaPresenceProps) {
  const ringRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);
  const reducedMotion = usePrefersReducedMotion();
  const Glyph = (archetype && ARCHETYPE_GLYPH[archetype]) || UserRound;

  useEffect(() => {
    if (reducedMotion || clientState !== "speaking") {
      ringRef.current?.style.setProperty("--amp", "0");
      return;
    }
    let cancelled = false;
    function tick() {
      if (cancelled) return;
      const amplitude = getAmplitude();
      ringRef.current?.style.setProperty("--amp", String(Math.min(1, amplitude * 3.5)));
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [clientState, getAmplitude, reducedMotion]);

  const clamped = Math.min(1, Math.max(0, progress ?? 0));

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative flex h-48 w-48 items-center justify-center sm:h-56 sm:w-56">
        {progress !== undefined && (
          <svg
            aria-hidden
            viewBox={`0 0 ${ARC_SIZE} ${ARC_SIZE}`}
            className="absolute inset-0 h-full w-full -rotate-90"
          >
            <circle cx={ARC_SIZE / 2} cy={ARC_SIZE / 2} r={ARC_RADIUS} fill="none" stroke="var(--border-subtle)" strokeWidth={2} />
            <circle
              cx={ARC_SIZE / 2}
              cy={ARC_SIZE / 2}
              r={ARC_RADIUS}
              fill="none"
              stroke="var(--text-tertiary)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeDasharray={ARC_CIRCUMFERENCE}
              strokeDashoffset={ARC_CIRCUMFERENCE * (1 - clamped)}
              className="transition-[stroke-dashoffset] duration-1000 ease-linear"
            />
          </svg>
        )}
        <div
          ref={ringRef}
          aria-hidden
          className={clsx(
            "flex h-40 w-40 items-center justify-center rounded-full border-2 transition-[border-color] duration-150 sm:h-48 sm:w-48",
            !reducedMotion && clientState === "your_turn" && "animate-pulse-gentle",
            !reducedMotion && clientState === "thinking" && "animate-thinking",
          )}
          style={
            {
              "--amp": 0,
              borderColor: clientState === "connection_trouble" ? "var(--status-bad)" : "var(--accent)",
              transform: reducedMotion ? undefined : "scale(calc(1 + var(--amp, 0) * 0.18))",
            } as React.CSSProperties
          }
        >
          <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full bg-[var(--bg-raised)] sm:h-32 sm:w-32">
            <Glyph size={36} strokeWidth={1.5} className="text-[var(--text-secondary)]" />
          </div>
        </div>
      </div>
      <div className="text-center">
        <p className="text-md font-medium">{personaName}</p>
        <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">{STATE_LABEL[clientState]}</p>
      </div>
    </div>
  );
}
