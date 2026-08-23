"use client";

import { useCallback, useRef, useState } from "react";

import { MicPermissionError } from "@/components/practice/mic-permission-error";
import { MicLevelMeter } from "@/components/practice/mic-level-meter";
import { Button } from "@/components/ui/button";
import { useAudioCapture } from "@/hooks/use-audio-capture";
import type { MicCaptureConstraints } from "@/lib/audio/capture";

const TEST_TONE_HZ = 440;
const TEST_TONE_MS = 600;

function playTestTone(): void {
  const AudioContextCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioContextCtor();
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.frequency.value = TEST_TONE_HZ;
  gain.gain.value = 0.15;
  oscillator.connect(gain).connect(ctx.destination);
  oscillator.start();
  oscillator.stop(ctx.currentTime + TEST_TONE_MS / 1000);
  oscillator.onended = () => void ctx.close();
}

/** Task 4.4's Settings > Audio "a re-runnable audio check" — a self-contained, local-only
 * mic + speaker check that doesn't require a live session (unlike the practice room's own
 * pre-flight overlay, which is inherently tied to a real WS connection, Task 3.2 AU-09).
 * Reuses the exact same capture hook and level meter the practice room uses, so "the check
 * passed" means the real capture path actually works, not a simulated stand-in. */
export function AudioCheckPanel({ constraints }: { constraints?: MicCaptureConstraints }) {
  const meterRef = useRef<HTMLDivElement>(null);
  const [heardSomething, setHeardSomething] = useState(false);
  const [playedTone, setPlayedTone] = useState(false);
  const [confirmed, setConfirmed] = useState<boolean | null>(null);

  const onLevel = useCallback((rms: number) => {
    if (rms > 0.02) setHeardSomething(true);
  }, []);

  const capture = useAudioCapture({
    onFrame: () => {}, // local-only check — frames are never sent anywhere
    meterElementRef: meterRef,
    onLevel,
    constraints,
  });

  if (
    capture.permission === "denied" ||
    capture.permission === "no_device" ||
    capture.permission === "revoked" ||
    capture.permission === "error"
  ) {
    return <MicPermissionError state={capture.permission} onRetry={() => void capture.start()} />;
  }

  return (
    <div className="rounded-lg border bg-[var(--bg-card)] p-4">
      <p className="text-sm font-medium">Audio check</p>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">
        Say something and watch the meter, then play a test tone to check your speakers.
      </p>

      <div className="mt-4 flex items-center gap-3">
        {capture.permission === "granted" ? (
          <Button variant="secondary" size="sm" onClick={() => void capture.stop()}>
            Stop mic check
          </Button>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void capture.start()}
            disabled={capture.permission === "requesting"}
          >
            {capture.permission === "requesting" ? "Requesting…" : "Start mic check"}
          </Button>
        )}
        <MicLevelMeter ref={meterRef} />
        {heardSomething && <span className="text-xs text-[var(--score-strong)]">We heard you</span>}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            playTestTone();
            setPlayedTone(true);
          }}
        >
          Play test tone
        </Button>
        {playedTone && confirmed === null && (
          <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
            <span>Did you hear that?</span>
            <button
              type="button"
              onClick={() => setConfirmed(true)}
              className="text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              Yes
            </button>
            <button
              type="button"
              onClick={() => setConfirmed(false)}
              className="text-[var(--danger)] hover:text-[var(--danger-hover)]"
            >
              No
            </button>
          </div>
        )}
        {confirmed === true && <span className="text-xs text-[var(--score-strong)]">Speakers working</span>}
        {confirmed === false && (
          <span className="text-xs text-[var(--score-weak)]">Check your output device below</span>
        )}
      </div>
    </div>
  );
}
