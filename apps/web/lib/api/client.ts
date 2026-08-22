/**
 * The frozen API error shape (CLAUDE.md §6):
 *   { "error": { "code", "message", "recovery", "fatal", "trace_id" } }
 *
 * `apiFetch` is the one place that shape gets parsed, one place a 401 triggers a silent
 * refresh-and-retry, and one place the API base URL is read from — every resource function in
 * `resources.ts` goes through this.
 */
import { useAuthStore } from "@/stores/auth-store";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly code: string;
  readonly recovery: string;
  readonly fatal: boolean;
  readonly traceId: string;
  readonly status: number;

  constructor(status: number, body: {
    code: string;
    message: string;
    recovery: string;
    fatal: boolean;
    trace_id: string;
  }) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.recovery = body.recovery;
    this.fatal = body.fatal;
    this.traceId = body.trace_id;
  }
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
}

let refreshInFlight: Promise<string | null> | null = null;

/** `POST /auth/refresh` rides the httpOnly cookie (`credentials: "include"`) — no body, no
 * Authorization header. De-duplicated: several components can independently discover an
 * expired token at once (a query refetch, a mutation, app bootstrap) and must not each fire
 * their own refresh call. */
async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!resp.ok) {
        useAuthStore.getState().clear();
        return null;
      }
      const body: TokenResponse = await resp.json();
      useAuthStore.getState().setToken(body.access_token, body.expires_in);
      return body.access_token;
    } catch {
      useAuthStore.getState().clear();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

/** Called once, on app boot, before anything else tries to fetch — see components/shell/auth-gate.tsx. */
export async function bootstrapAuth(): Promise<boolean> {
  const token = await refreshAccessToken();
  return token !== null;
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip the Authorization header and the 401-retry entirely — only /auth/* endpoints need this. */
  anonymous?: boolean;
}

async function doFetch(path: string, token: string | null, options: ApiFetchOptions): Promise<Response> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (token && !options.anonymous) headers.set("Authorization", `Bearer ${token}`);

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
}

/** The one function every typed resource call in resources.ts goes through. On a 401 that isn't
 * itself a retry, refreshes once and retries once — never loops, never retries a second time. */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const token = options.anonymous ? null : useAuthStore.getState().accessToken;
  let resp = await doFetch(path, token, options);

  if (resp.status === 401 && !options.anonymous) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      resp = await doFetch(path, refreshed, options);
    }
  }

  if (!resp.ok) {
    let body;
    try {
      body = await resp.json();
    } catch {
      throw new ApiError(resp.status, {
        code: "ORCHESTRATION_INTERNAL_ERROR",
        message: resp.statusText || "Request failed.",
        recovery: "Try again in a moment.",
        fatal: false,
        trace_id: "",
      });
    }
    throw new ApiError(resp.status, body.error ?? body);
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}
