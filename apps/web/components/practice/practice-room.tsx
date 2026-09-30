"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, WifiOff } from "lucide-react";
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
import { PracticeRoomSkeleton } from "./practice-room-skeleton";
import { PreflightOverlay } from "./preflight-overlay";
import { SessionTimer } from "./session-timer";
import { TurnIndicator } from "./turn-indicator";

const PREFLIGHT_DONE_KEY = "interactai-preflight-done";
const startKey = (sessionId: string) => `interactai-session-start-${sessionId}`;

function readStoredStart(sessionId: string): number | null {
  try {
    const raw = sessionStorage.getItem(startKey(sessionId));
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

/** docs/ui-audit-2026-09.md §7: elapsed time is *derived* from when the session started, never
 * accumulated tick by tick — `setInterval(+1000)` drifted, and restarted at 0 after a reload or a
 * reconnect. The start is this tab's own first-connect timestamp (same clock as `Date.now()`,
 * kept in sessionStorage so a reload continues from it), falling back to the server's
 * `started_at` in a fresh tab. The interval only re-renders; it never adds anything up. */
function useElapsedMs(sessionId: string, serverStartedAt: string | null | undefined, running: boolean): number {
  const [startMs, setStartMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const stored = readStoredStart(sessionId);
    if (stored) setStartMs(stored);
    else if (serverStartedAt) setStartMs(Date.parse(serverStartedAt));
  }, [sessionId, serverStartedAt]);

  useEffect(() => {
    if (!running) return;
    if (readStoredStart(sessionId) === null) {
      const now = Date.now();
      const fromServer = serverStartedAt ? Date.parse(serverStartedAt) : null;
      const start = fromServer && fromServer <= now ? fromServer : now;
      try {
        sessionStorage.setItem(startKey(sessionId), String(start));
      } catch {
        // ignore — the in-memory start below still keeps this tab's timer right
      }
      setStartMs(start);
    }
    setNowMs(Date.now());
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running, sessionId, serverStartedAt]);

  return startMs === null ? 0 : Math.max(0, nowMs - startMs);
}

function FullPageMessage({ title, body, icon }: { title: string; body?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex h-dvh w-full flex-col items-center justify-center gap-2 bg-[var(--bg-page)] px-6 text-center animate-fade-in">
      {icon}
      <p className="text-md font-medium">{title}</p>
      {body && <div className="max-w-sm text-sm text-[var(--text-secondary)]">{body}</div>}
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
  const answersGiven = usePracticeStore((s) => s.answersGiven);
  const reset = usePracticeStore((s) => s.reset);
  const queryClient = useQueryClient();

  const [muted, setMutedState] = useState(false);
  const [showEndDialog, setShowEndDialog] = useState(false);
  const elapsedMs = useElapsedMs(
    sessionId,
    session?.started_at,
    (connection === "connected" || connection === "reconnecting") && !ended,
  );
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

  // The session row gets its server `started_at` once realtime accepts the connection; refresh it
  // once so a later reload in a new tab has the true start to fall back on.
  const refreshedStartRef = useRef(false);
  useEffect(() => {
    if (connection !== "connected" || refreshedStartRef.current || session?.started_at) return;
    refreshedStartRef.current = true;
    void queryClient.invalidateQueries({ queryKey: ["sessions", sessionId], exact: true });
  }, [connection, session?.started_at, queryClient, sessionId]);

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

  // docs/ui-audit-2026-09.md §7: M mutes, C toggles captions, Esc *opens* the end-session
  // confirmation (it never ends the session by itself — Task 3.2 non-negotiable #5).
  const showEndDialogRef = useRef(showEndDialog);
  showEndDialogRef.current = showEndDialog;
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog'], [role='alertdialog']")) return;
      if (showEndDialogRef.current || usePracticeStore.getState().ended) return;
      const key = e.key.toLowerCase();
      if (key === "m") {
        e.preventDefault();
        toggleMute();
      } else if (key === "c") {
        e.preventDefault();
        setCaptionsEnabled(!useShellStore.getState().captionsEnabled);
      } else if (e.key === "Escape") {
        e.preventDefault();
        setShowEndDialog(true);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [toggleMute, setCaptionsEnabled]);

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

  if (connection === "at_capacity") {
    return (
      <FullPageMessage
        title="At capacity, try again shortly"
        body="Every practice slot on this server is in use. Nothing was recorded; try again in a minute."
      />
    );
  }

  if (!session || !scenario) {
    return <PracticeRoomSkeleton />;
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
    <div className="relative flex h-dvh flex-col items-center justify-center gap-8 bg-[var(--bg-page)] px-6 animate-fade-in">
      <div className="absolute left-1/2 top-6 -translate-x-1/2 text-center">
        <p className="mb-1 truncate text-xs text-[var(--text-tertiary)]">{scenario.title}</p>
        <SessionTimer elapsedMs={elapsedMs} targetMinutes={session.target_minutes} />
      </div>

      {connection === "reconnecting" && (
        <div
          role="status"
          className="absolute top-20 flex items-center gap-1.5 rounded-full border border-[var(--status-bad)] px-3 py-1 text-xs text-[var(--status-bad)] animate-fade-in"
        >
          <WifiOff size={12} aria-hidden /> Connection trouble — reconnecting…
        </div>
      )}

      <PersonaPresence
        personaName={persona?.name ?? scenario.title}
        archetype={persona?.archetype}
        clientState={clientState}
        getAmplitude={getPlaybackAmplitude}
        progress={elapsedMs / (session.target_minutes * 60_000)}
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

      <EndSessionDialog
        open={showEndDialog}
        onCancel={() => setShowEndDialog(false)}
        onConfirm={() => {
          setShowEndDialog(false);
          endSession();
        }}
      />

      {showPreflight && <PreflightOverlay onDismiss={dismissPreflight} />}

      {ended && (
        <div className="fixed inset-0 z-40">
          <FullPageMessage
            icon={<CheckCircle2 size={28} aria-hidden className="mb-1 text-[var(--status-ok)]" />}
            title="Session saved"
            body={
              <>
                <p className="font-mono text-xs text-[var(--text-tertiary)]">
                  {answersGiven} {answersGiven === 1 ? "answer" : "answers"} · {Math.max(1, Math.round(elapsedMs / 60_000))} min
                </p>
                <p className="mt-2">Taking you to the report…</p>
              </>
            }
          />
        </div>
      )}
    </div>
  );
}
