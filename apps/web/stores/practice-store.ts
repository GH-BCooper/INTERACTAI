import { create } from "zustand";

import type { ClientState } from "@/lib/ws-types";

/** Task 3.2: everything the practice room island needs, EXCEPT the mic level (that bypasses
 * React entirely — see hooks/use-audio-capture.ts) and the speaking-ring amplitude (same, see
 * hooks/use-playback-amplitude.ts). Zustand, not Context, so a caption update at conversational
 * pace doesn't re-render the timer, and a timer tick doesn't re-render the caption
 * (docs/phase-3-LEARN.md §3). */

export type ConnectionUiState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "session_busy"
  | "at_capacity"
  | "ended";

export type CaptionSpeaker = "user" | "persona" | null;

interface PracticeState {
  clientState: ClientState;
  connection: ConnectionUiState;
  captionText: string;
  captionSpeaker: CaptionSpeaker;
  elapsedMs: number;
  muted: boolean;
  ended: boolean;
  endReason: string | null;
  reportPending: boolean;
  distressExitPending: boolean;
  personaTurnBuffer: string;

  setClientState: (s: ClientState) => void;
  setConnection: (c: ConnectionUiState) => void;
  setUserPartialCaption: (text: string) => void;
  appendPersonaCaption: (delta: string, done: boolean) => void;
  clearCaption: () => void;
  setElapsedMs: (ms: number) => void;
  setMuted: (m: boolean) => void;
  setEnded: (reason: string, reportPending: boolean) => void;
  setDistressExitPending: (pending: boolean) => void;
  reset: () => void;
}

const INITIAL = {
  clientState: "your_turn" as ClientState,
  connection: "connecting" as ConnectionUiState,
  captionText: "",
  captionSpeaker: null as CaptionSpeaker,
  elapsedMs: 0,
  muted: false,
  ended: false,
  endReason: null as string | null,
  reportPending: false,
  distressExitPending: false,
  personaTurnBuffer: "",
};

export const usePracticeStore = create<PracticeState>((set, get) => ({
  ...INITIAL,

  setClientState: (clientState) => set({ clientState }),
  setConnection: (connection) => set({ connection }),

  setUserPartialCaption: (text) => set({ captionText: text, captionSpeaker: "user" }),

  appendPersonaCaption: (delta, done) => {
    const next = done ? "" : get().personaTurnBuffer + delta;
    set({
      personaTurnBuffer: next,
      captionText: done ? get().personaTurnBuffer : next,
      captionSpeaker: "persona",
    });
  },

  clearCaption: () => set({ captionText: "", captionSpeaker: null, personaTurnBuffer: "" }),

  setElapsedMs: (elapsedMs) => set({ elapsedMs }),
  setMuted: (muted) => set({ muted }),

  setEnded: (endReason, reportPending) =>
    set({ ended: true, endReason, reportPending, clientState: "ended", connection: "ended" }),

  setDistressExitPending: (distressExitPending) => set({ distressExitPending }),

  reset: () => set(INITIAL),
}));
