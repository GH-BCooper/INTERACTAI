"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAudioCapture } from "@/hooks/use-audio-capture";
import { useRealtimeSocket } from "@/hooks/use-realtime-socket";
import { ApiError } from "@/lib/api/client";
import { useMe, usePersonas, useScenario, useSession } from "@/lib/api/hooks";
import { getSavedInputDeviceId } from "@/lib/audio/device-prefs";
import { useShellStore } from "@/stores/shell-store";
import { usePracticeStore } from "@/stores/practice-store";

import { CaptionLine } from "./caption-line";
import { Controls } from "./controls";
import { EndSessionDialog } from "./end-session-dialog";
import { MicPermissionError } from "./mic-permission-error";
import { PersonaPresence } from "./persona-presence";
import { PreflightOverlay } from "./preflight-overlay";
import { SessionTimer } from "./session-timer";
import { TurnIndicator } from "./turn-indicator";

const PREFLIGHT_DONE_KEY = "interactai-preflight-done";

function FullPageMessage({ title, body }: { title: string; body?: string }) {
  return (
    <div className="flex h-dvh w-full flex-col items-center justify-center gap-2 bg-[var(--bg-page)] px-6 text-center">
      <p className="text-md font-medium">{title}</p>
      {body && <p className="max-w-sm text-sm text-[var(--text-secondary)]">{body}</p>}
    </div>
  );
}

/** Task 3.2 — THE ONLY CLIENT BOUNDARY on the practice room route. Everything below here is
 * client: mic capture, the WS connection, audio playback and every piece of visible state.
 * No sidebar, no breadcrumb, no top bar — deliberately a different surface than the rest of the
 * authenticated app (docs/phase-3-LEARN.md §2). */
export function PracticeRoom({
  sessionId,
  micDeniedExit,
}: {
  sessionId: string;
  /** Task 4.3's onboarding edge case: "Mic denied at step 3 -> ... a 'skip for now' that
   * clearly explains they cannot practise yet." Optional and additive — every other caller of
   * PracticeRoom omits this and MicPermissionError renders exactly as it did before. */
  micDeniedExit?: { label: string; href: string };
}) {
  const router = useRouter();
  const { data: session, error: sessionError } = useSession(sessionId);
  const { data: scenario } = useScenario(session?.scenario_id);
  const { data: personas } = usePersonas();
  const { data: me } = useMe();

  const captionsEnabled = useShellStore((s) => s.captionsEnabled);
  const setCaptionsEnabled = useShellStore((s) => s.setCaptionsEnabled);
  const seedCaptionsDefault = useShellStore((s) => s.seedCaptionsDefault);

  useEffect(() => {
    if (me?.profile) seedCaptionsDefault(me.profile.captions_default);
  }, [me, seedCaptionsDefault]);

  const clientState = usePracticeStore((s) => s.clientState);
  const connection = usePracticeStore((s) => s.connection);
  const captionText = usePracticeStore((s) => s.captionText);
  const ended = usePracticeStore((s) => s.ended);
  const reset = usePracticeStore((s) => s.reset);

  const [muted, setMutedState] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [showEndDialog, setShowEndDialog] = useState(false);
  const [showPreflight, setShowPreflight] = useState(false);

  const meterRef = useRef<HTMLDivElement>(null);
  const { sendAudioFrame, observeMicRms, endSession, getPlaybackAmplitude } =
    useRealtimeSocket(sessionId);

  const onFrame = useCallback((frame: ArrayBuffer) => sendAudioFrame(frame), [sendAudioFrame]);
  // Task 4.4's Settings > Audio page: the account's echo-cancellation/noise-suppression
  // preferences (server-persisted) plus the browser-local saved input device, if any. Both
  // default to the previous hardcoded behaviour when unset, so a user who has never opened
  // Settings gets exactly what they got before this existed.
  const captureConstraints = useMemo(
    () => ({
      deviceId: getSavedInputDeviceId() ?? undefined,
      echoCancellation: me?.profile?.echo_cancellation,
      noiseSuppression: me?.profile?.noise_suppression,
    }),
    [me],
  );
  const capture = useAudioCapture({
    onFrame,
    meterElementRef: meterRef,
    onLevel: observeMicRms,
    constraints: captureConstraints,
  });

  // Task 3.2 non-negotiable #1's meter also feeds the client-side barge-in guard
  // (hooks/use-realtime-socket.ts) — same RMS stream, two independent consumers.
  const startedRef = useRef(false);
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void capture.start();
    return () => {
      void capture.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- start once, on mount, regardless
  }, []);

  useEffect(() => {
    if (typeof localStorage === "undefined") return;
    if (localStorage.getItem(PREFLIGHT_DONE_KEY)) return;
    setShowPreflight(true);
  }, []);

  const dismissPreflight = useCallback(() => {
    setShowPreflight(false);
    try {
      localStorage.setItem(PREFLIGHT_DONE_KEY, "1");
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (connection !== "connected" || ended) return;
    const timer = setInterval(() => setElapsedMs((ms) => ms + 1000), 1000);
    return () => clearInterval(timer);
  }, [connection, ended]);

  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (ended) return;
      // Task 3.2 non-negotiable #6: confirm before losing the tab. The recording itself is
      // already durable — services/realtime uploads incrementally during the session
      // (docs/phase-2-BUILD.md TASK 2.2c) — so there is nothing additional to flush from here.
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [ended]);

  useEffect(() => {
    if (ended) {
      const timer = setTimeout(() => router.replace(`/app/sessions/${sessionId}`), 1200);
      return () => clearTimeout(timer);
    }
  }, [ended, router, sessionId]);

  useEffect(() => reset, [reset]);

  useEffect(() => {
    // Task 3.2 edge case: "Session already ended -> Redirect to the report."
    if (session?.status === "closed") router.replace(`/app/sessions/${sessionId}`);
  }, [session?.status, router, sessionId]);

  const toggleMute = useCallback(() => {
    setMutedState((m) => {
      const next = !m;
      capture.setMuted(next);
      return next;
    });
  }, [capture]);

  const persona = useMemo(
    () => personas?.find((p) => p.id === scenario?.persona_id) ?? null,
    [personas, scenario],
  );

  if (sessionError instanceof ApiError && (sessionError.status === 404 || sessionError.status === 403)) {
    return <FullPageMessage title="Session not found" />;
  }

  if (session?.status === "closed") {
    return <FullPageMessage title="This session already ended" body="Taking you to the report…" />;
  }

  if (connection === "session_busy") {
    return (
      <FullPageMessage
        title="This session is open elsewhere"
        body="Close the other tab or device to continue here."
      />
    );
  }

  if (!session || !scenario) {
    return <FullPageMessage title="Loading your session…" />;
  }

  if (capture.permission === "denied" || capture.permission === "no_device" || capture.permission === "revoked" || capture.permission === "error") {
    return (
      <MicPermissionError
        state={capture.permission}
        onRetry={() => void capture.start()}
        secondaryAction={micDeniedExit}
      />
    );
  }

  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-8 bg-[var(--bg-page)] px-6">
      <div className="absolute left-1/2 top-6 -translate-x-1/2">
        <SessionTimer elapsedMs={elapsedMs} targetMinutes={session.target_minutes} />
      </div>

      {connection === "reconnecting" && (
        <div
          role="status"
          className="absolute top-16 rounded-full border border-[var(--danger)] px-3 py-1 text-xs text-[var(--danger)]"
        >
          Connection trouble — reconnecting…
        </div>
      )}

      <PersonaPresence
        personaName={persona?.name ?? scenario.title}
        clientState={clientState}
        getAmplitude={getPlaybackAmplitude}
      />

      <CaptionLine text={captionText} enabled={captionsEnabled} />

      <TurnIndicator clientState={clientState} />

      <div className="absolute bottom-8">
        <Controls
          muted={muted}
          onToggleMute={toggleMute}
          captionsEnabled={captionsEnabled}
          onToggleCaptions={() => setCaptionsEnabled(!captionsEnabled)}
          onEndClick={() => setShowEndDialog(true)}
          meterRef={meterRef}
        />
      </div>

      {showEndDialog && (
        <EndSessionDialog
          onCancel={() => setShowEndDialog(false)}
          onConfirm={() => {
            setShowEndDialog(false);
            endSession();
          }}
        />
      )}

      {showPreflight && <PreflightOverlay onDismiss={dismissPreflight} />}

      {ended && <FullPageMessage title="Session saved" body="Taking you to the report…" />}
    </div>
  );
}
