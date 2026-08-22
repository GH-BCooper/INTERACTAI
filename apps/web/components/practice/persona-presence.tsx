"use client";

import { clsx } from "clsx";
import { useEffect, useRef } from "react";

import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";
import type { ClientState } from "@/lib/ws-types";

interface PersonaPresenceProps {
  personaName: string;
  clientState: ClientState;
  getAmplitude: () => number;
}

const STATE_LABEL: Record<ClientState, string> = {
  your_turn: "Your turn",
  thinking: "Thinking",
  speaking: "Speaking",
  connection_trouble: "Reconnecting",
  ended: "Session ended",
};

/** Task 3.2: "One large circular element with the persona's name and an amplitude-reactive
 * ring" — listening pulses gently (CSS animation), thinking gets its own restrained animation
 * (never a spinner — docs/phase-3-LEARN.md §2: "a spinner says the software is loading"), and
 * speaking is driven by *real* playback amplitude, sampled every frame and written straight to
 * a CSS custom property on the ring element — never through React state (same discipline as
 * the mic meter). */
export function PersonaPresence({ personaName, clientState, getAmplitude }: PersonaPresenceProps) {
  const ringRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);
  const reducedMotion = usePrefersReducedMotion();

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

  return (
    <div className="flex flex-col items-center gap-4">
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
            borderColor: clientState === "connection_trouble" ? "var(--danger)" : "var(--accent)",
            transform: reducedMotion ? undefined : "scale(calc(1 + var(--amp, 0) * 0.18))",
          } as React.CSSProperties
        }
      >
        <div className="flex h-28 w-28 items-center justify-center rounded-full bg-[var(--bg-raised)] text-2xl font-medium sm:h-32 sm:w-32">
          {personaName.charAt(0).toUpperCase()}
        </div>
      </div>
      <div className="text-center">
        <p className="text-md font-medium">{personaName}</p>
        {reducedMotion && (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">{STATE_LABEL[clientState]}</p>
        )}
      </div>
    </div>
  );
}
