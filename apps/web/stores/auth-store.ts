import { create } from "zustand";

interface AuthState {
  accessToken: string | null;
  expiresAt: number | null; // epoch ms
  status: "unknown" | "authenticated" | "anonymous";
  setToken: (token: string, expiresInSeconds: number) => void;
  clear: () => void;
}

/** The access token lives in memory only — never localStorage — so an XSS payload gains
 * nothing more than it would from reading React state anyway, and a closed tab genuinely
 * forgets it. The refresh token is a separate, httpOnly, api-domain-scoped cookie the browser
 * carries automatically (services/api/app/routers/auth.py); `lib/api/client.ts` uses it via
 * `POST /auth/refresh` to obtain a fresh access token on load and after a 401. */
export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  expiresAt: null,
  status: "unknown",
  setToken: (token, expiresInSeconds) =>
    set({
      accessToken: token,
      expiresAt: Date.now() + expiresInSeconds * 1000,
      status: "authenticated",
    }),
  clear: () => set({ accessToken: null, expiresAt: null, status: "anonymous" }),
}));
