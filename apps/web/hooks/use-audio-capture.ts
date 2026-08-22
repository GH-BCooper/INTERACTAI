"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { createMicCapture, type MicCaptureHandle } from "@/lib/audio/capture";

export type MicPermissionState =
  | "unknown"
  | "requesting"
  | "granted"
  | "denied"
  | "no_device"
  | "revoked"
  | "error";

interface UseAudioCaptureOptions {
  /** Called with each 652-byte wire frame, ready to send over the WS. */
  onFrame: (wireFrame: ArrayBuffer) => void;
  /** Task 3.2 non-negotiable #1: the level meter "must not go through React state" — this
   * writes `--level` directly onto whatever element the caller points it at, at whatever rate
   * the worklet posts meter messages (>= 20Hz), completely bypassing React's render cycle. */
  meterElementRef: React.RefObject<HTMLElement | null>;
  /** A second, independent consumer of the same RMS stream that genuinely needs the numeric
   * value (the practice room's client-side barge-in guard) — kept separate from the DOM write
   * above rather than having that consumer read the value back out of a CSS custom property. */
  onLevel?: (rms: number) => void;
}

export interface UseAudioCapture {
  permission: MicPermissionState;
  errorDetail: string | null;
  /** Requests getUserMedia and starts capture. Safe to call again after `stop()`. */
  start: () => Promise<void>;
  stop: () => Promise<void>;
  setMuted: (muted: boolean) => void;
}

/** Task 3.2's three device edge cases wrapped around lib/audio/capture.ts's already-built
 * getUserMedia/AudioWorklet glue: permission denial (with the browser detected so the caller
 * can show browser-specific recovery instructions), permission revoked mid-session (the
 * MediaStreamTrack's own `ended` event — the only reliable cross-browser signal for this), and
 * a device change mid-session (`navigator.mediaDevices.ondevicechange`, re-acquire and notify
 * calmly rather than silently going deaf). */
export function useAudioCapture({
  onFrame,
  meterElementRef,
  onLevel,
}: UseAudioCaptureOptions): UseAudioCapture {
  const [permission, setPermission] = useState<MicPermissionState>("unknown");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const handleRef = useRef<MicCaptureHandle | null>(null);
  const mutedRef = useRef(false);
  const stoppedRef = useRef(false);
  const onLevelRef = useRef(onLevel);
  onLevelRef.current = onLevel;

  const handleMeter = useCallback(
    (rms: number) => {
      meterElementRef.current?.style.setProperty("--level", String(rms));
      onLevelRef.current?.(rms);
    },
    [meterElementRef],
  );

  const start = useCallback(async (): Promise<void> => {
    stoppedRef.current = false;
    setPermission("requesting");
    setErrorDetail(null);
    try {
      const handle = await createMicCapture({
        onFrame,
        onMeter: handleMeter,
        onTrackEnded: () => {
          // The OS/browser pulled mic access out from under an already-running capture — pause
          // rather than silently going deaf, and let the UI offer a one-click resume.
          meterElementRef.current?.style.setProperty("--level", "0");
          handleRef.current = null;
          setPermission("revoked");
        },
      });
      if (stoppedRef.current) {
        // stop() was called while getUserMedia was still resolving.
        await handle.stop();
        return;
      }
      handle.setMuted(mutedRef.current);
      handleRef.current = handle;
      setPermission("granted");
    } catch (err) {
      const name = err instanceof DOMException ? err.name : "";
      if (name === "NotAllowedError" || name === "SecurityError") setPermission("denied");
      else if (name === "NotFoundError" || name === "OverconstrainedError") setPermission("no_device");
      else setPermission("error");
      setErrorDetail(err instanceof Error ? err.message : String(err));
    }
  }, [onFrame, handleMeter, meterElementRef]);

  const stop = useCallback(async (): Promise<void> => {
    stoppedRef.current = true;
    meterElementRef.current?.style.setProperty("--level", "0");
    const handle = handleRef.current;
    handleRef.current = null;
    if (handle) await handle.stop();
  }, [meterElementRef]);

  const setMuted = useCallback((muted: boolean) => {
    mutedRef.current = muted;
    handleRef.current?.setMuted(muted);
  }, []);

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices) return;
    function onDeviceChange(): void {
      if (permission !== "granted") return;
      // Task 3.2 edge case: "Device changes mid-session (headphones unplugged) -> detect
      // devicechange, re-acquire, notify calmly." Re-acquiring is the safest general response —
      // the previous MediaStreamTrack may already be dead (its `ended` event fires around the
      // same time), and a fresh getUserMedia call picks up whatever the OS now considers the
      // default input.
      void stop().then(() => start());
    }
    navigator.mediaDevices.addEventListener("devicechange", onDeviceChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", onDeviceChange);
  }, [permission, start, stop]);

  useEffect(() => {
    return () => {
      void stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unmount-only cleanup
  }, []);

  return { permission, errorDetail, start, stop, setMuted };
}
