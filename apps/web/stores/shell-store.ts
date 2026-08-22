import { create } from "zustand";

interface ShellState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  commandPaletteOpen: boolean;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
  /** Task 3.2 caption toggle — "Optional, remembered per user." Kept here (not per-session
   * state) since it belongs to the person, not the practice session. */
  captionsEnabled: boolean;
  setCaptionsEnabled: (enabled: boolean) => void;
}

const CAPTIONS_KEY = "interactai-captions-enabled";
const SIDEBAR_KEY = "interactai-sidebar-collapsed";

function readBool(key: string, fallback: boolean): boolean {
  if (typeof localStorage === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : raw === "true";
  } catch {
    return fallback;
  }
}

function writeBool(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // ignore
  }
}

export const useShellStore = create<ShellState>((set, get) => ({
  sidebarCollapsed: readBool(SIDEBAR_KEY, false),
  toggleSidebar: () => {
    const next = !get().sidebarCollapsed;
    set({ sidebarCollapsed: next });
    writeBool(SIDEBAR_KEY, next);
  },
  commandPaletteOpen: false,
  openCommandPalette: () => set({ commandPaletteOpen: true }),
  closeCommandPalette: () => set({ commandPaletteOpen: false }),
  captionsEnabled: readBool(CAPTIONS_KEY, true),
  setCaptionsEnabled: (enabled) => {
    set({ captionsEnabled: enabled });
    writeBool(CAPTIONS_KEY, enabled);
  },
}));
