"use client";

import { useCallback, useEffect, useRef } from "react";

import { INTERRUPT_GUARD_MS, InterruptGuard, PersonaPlayback } from "@/lib/audio/playback";
import { sessions } from "@/lib/api/resources";
import { AudioTextCorrelator } from "@/lib/realtime/audio-text-correlator";
import { RealtimeConnection, type ConnectionStatus } from "@/lib/realtime/connection";
import { usePracticeStore } from "@/stores/practice-store";
import { useToastStore } from "@/stores/toast-store";
import type { WsMessage } from "@/lib/ws-types";

const CLIENT_SAMPLE_RATE = 16_000;
const CLIENT_FRAME_MS = 20;
// A heuristic, not the server's real Silero VAD threshold (docs/phase-1-BUILD.md TASK 1.3) —
// this only decides how early the *client* stops local playback on barge-in; the server's own
// interrupt detection (services/realtime/app/frame_pipeline.py::handle_interrupt_window) is the
// authoritative one and always confirms via the `interrupted` message regardless of whether
// this fires first.
const LOCAL_VOICED_RMS_THRESHOLD = 0.02;

export interface UseRealtimeSocket {
  sendAudioFrame: (wireFrame: ArrayBuffer) => void;
  observeMicRms: (rms: number) => void;
  endSession: () => void;
  getPlaybackAmplitude: () => number;
}

/** Wires lib/realtime/connection.ts + lib/realtime/audio-text-correlator.ts +
 * lib/audio/playback.ts to the practice store — the orchestration layer for Task 3.2's WS
 * lifecycle. One instance per mounted practice room; everything here is a ref, not React
 * state, since none of it should ever trigger a re-render on its own (the store updates it
 * calls are the only thing components subscribe to). */
export function useRealtimeSocket(sessionId: string): UseRealtimeSocket {
  const connectionRef = useRef<RealtimeConnection | null>(null);
  const playbackRef = useRef<PersonaPlayback | null>(null);
  const correlatorRef = useRef(new AudioTextCorrelator());
  const pendingAudioRef = useRef(new Map<number, { payload: Int16Array; sampleRate: number }>());
  const interruptGuardRef = useRef(new InterruptGuard(INTERRUPT_GUARD_MS, CLIENT_FRAME_MS));
  const clientStateRef = useRef(usePracticeStore.getState().clientState);

  const setClientState = usePracticeStore((s) => s.setClientState);
  const setConnection = usePracticeStore((s) => s.setConnection);
  const setUserPartialCaption = usePracticeStore((s) => s.setUserPartialCaption);
  const appendPersonaCaption = usePracticeStore((s) => s.appendPersonaCaption);
  const setEnded = usePracticeStore((s) => s.setEnded);
  const setDistressExitPending = usePracticeStore((s) => s.setDistressExitPending);
  const pushToast = useToastStore((s) => s.push);

  useEffect(() => {
    return usePracticeStore.subscribe((state) => {
      clientStateRef.current = state.clientState;
    });
  }, []);

  const flushCompletedChunk = useCallback((seq: number, text: string) => {
    const audio = pendingAudioRef.current.get(seq);
    if (!audio) return;
    pendingAudioRef.current.delete(seq);
    playbackRef.current?.enqueueChunk(seq, audio.payload, text);
  }, []);

  const handleMessage = useCallback(
    (msg: WsMessage) => {
      switch (msg.type) {
        case "ready":
          break;
        case "state_change":
          // Task 3.2: "Map from state_change.client_state only — do not re-derive machine
          // states in the frontend."
          setClientState(msg.client_state);
          if (msg.client_state !== "speaking") interruptGuardRef.current.reset();
          break;
        case "partial_transcript":
          setUserPartialCaption(msg.text);
          break;
        case "turn_finalized":
          break;
        case "audio_chunk_meta":
          correlatorRef.current.observeMeta(msg.turn_id);
          break;
        case "persona_text":
          if (msg.done) {
            appendPersonaCaption("", true);
          } else {
            appendPersonaCaption(msg.text_delta, false);
            const completed = correlatorRef.current.observeText(msg.text_delta);
            if (completed) flushCompletedChunk(completed.seq, completed.text);
          }
          break;
        case "interrupted":
          playbackRef.current?.interrupt();
          break;
        case "degraded":
          pushToast({
            title: "Connection trouble",
            description: msg.message,
          });
          break;
        case "latency_report":
          break;
        case "session_closed":
          setEnded(msg.reason, msg.report_pending);
          if (msg.reason === "distress_exit") setDistressExitPending(false);
          break;
        case "error":
          if (msg.fatal) {
            pushToast({ title: "Session error", description: msg.message });
          }
          break;
        case "pong":
          break;
      }
    },
    [
      setClientState,
      setUserPartialCaption,
      appendPersonaCaption,
      setEnded,
      setDistressExitPending,
      pushToast,
      flushCompletedChunk,
    ],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;

    const playback = new PersonaPlayback();
    playbackRef.current = playback;

    const conn = new RealtimeConnection(
      {
        onStatusChange: (status: ConnectionStatus) => {
          const mapped = {
            connecting: "connecting",
            open: "connected",
            reconnecting: "reconnecting",
            session_busy: "session_busy",
            closed: "ended",
            fatal_error: "ended",
          } as const;
          setConnection(mapped[status]);
        },
        onMessage: handleMessage,
        onAudioFrame: (payload, sampleRate, seq) => {
          pendingAudioRef.current.set(seq, { payload, sampleRate });
          const completed = correlatorRef.current.observeFrame(seq);
          if (completed) flushCompletedChunk(completed.seq, completed.text);
        },
        mintWsUrl: async () => (await sessions.mintWsToken(sessionId)).ws_url,
      },
      (url) => new WebSocket(url),
      { sessionId, clientSampleRate: CLIENT_SAMPLE_RATE, clientFrameMs: CLIENT_FRAME_MS },
    );
    connectionRef.current = conn;
    void conn.connect();

    return () => {
      conn.close();
      playback.interrupt();
      connectionRef.current = null;
      playbackRef.current = null;
    };
    // Intentionally only depends on sessionId — handleMessage/flushCompletedChunk close over
    // refs and store setters, both stable across renders, and re-running this effect for those
    // would tear down and reopen the live connection for no reason.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const sendAudioFrame = useCallback((wireFrame: ArrayBuffer) => {
    connectionRef.current?.sendAudioFrame(wireFrame);
  }, []);

  const observeMicRms = useCallback((rms: number) => {
    if (clientStateRef.current !== "speaking") return;
    const guard = interruptGuardRef.current;
    if (rms > LOCAL_VOICED_RMS_THRESHOLD) {
      if (guard.observeVoicedFrame()) playbackRef.current?.interrupt();
    } else {
      guard.observeSilentFrame();
    }
  }, []);

  const endSession = useCallback(() => {
    connectionRef.current?.endSession("user_hangup");
  }, []);

  const getPlaybackAmplitude = useCallback(() => playbackRef.current?.getAmplitude() ?? 0, []);

  return { sendAudioFrame, observeMicRms, endSession, getPlaybackAmplitude };
}
