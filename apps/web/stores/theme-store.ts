import { create } from "zustand";

export type ThemePreference = "dark" | "light" | "system";

interface ThemeState {
  preference: ThemePreference;
  setPreference: (pref: ThemePreference) => void;
  toggle: () => void;
}

const STORAGE_KEY = "interactai-theme";

function applyToDom(pref: ThemePreference): void {
  if (typeof document === "undefined") return;
  if (pref === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", pref);
}

function readInitial(): ThemePreference {
  if (typeof localStorage === "undefined") return "system";
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Command palette's "toggle theme" verb (Task 3.1) and the settings page both read/write this.
 * The inline script in app/layout.tsx already applied the persisted choice before hydration —
 * this store's initial state just needs to agree with what's already on the DOM. */
export const useThemeStore = create<ThemeState>((set, get) => ({
  preference: readInitial(),
  setPreference: (pref) => {
    set({ preference: pref });
    applyToDom(pref);
    try {
      if (pref === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      // Private browsing / storage disabled — the choice just won't survive a reload.
    }
  },
  toggle: () => {
    const current = get().preference;
    const effectiveDark = current === "dark" || (current === "system" && systemPrefersDark());
    get().setPreference(effectiveDark ? "light" : "dark");
  },
}));
