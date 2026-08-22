import { create } from "zustand";

/** Task 3.4a: "One source of truth: playheadMs in a Zustand store. Everything derives from it."
 * No component holds its own notion of "where we are" — the waveform, transcript, score panel
 * and turn detail all read `playheadMs` from here and derive the current turn themselves (see
 * lib/report/derive-current-turn.ts), rather than being told which turn is active. */
interface PlayerState {
  playheadMs: number;
  isPlaying: boolean;
  activeCriterion: string | null;
  setPlayheadMs: (ms: number) => void;
  setIsPlaying: (playing: boolean) => void;
  setActiveCriterion: (key: string | null) => void;
}

export const usePlayerStore = create<PlayerState>((set) => ({
  playheadMs: 0,
  isPlaying: false,
  activeCriterion: null,
  setPlayheadMs: (playheadMs) => set({ playheadMs }),
  setIsPlaying: (isPlaying) => set({ isPlaying }),
  setActiveCriterion: (activeCriterion) => set({ activeCriterion }),
}));
