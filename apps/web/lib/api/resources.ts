import { apiFetch } from "./client";
import type {
  AnnotationOut,
  Difficulty,
  MeOut,
  Page,
  PersonaOut,
  RecordingOut,
  ReplayTokenOut,
  ReportOut,
  RubricOut,
  ScenarioOut,
  SessionOut,
  SessionScoreOut,
  TurnOut,
  WsTokenOut,
} from "./types";

export const me = {
  get: () => apiFetch<MeOut>("/me"),
  updateProfile: (body: { resume_text?: string | null; target_role?: string | null; clear_resume?: boolean }) =>
    apiFetch<MeOut["profile"]>("/me/profile", { method: "PATCH", body }),
  delete: () => apiFetch<void>("/me", { method: "DELETE" }),
};

export const scenarios = {
  list: (filters?: { family?: string; difficulty?: string; duration?: number; tag?: string }) => {
    const params = new URLSearchParams();
    if (filters?.family) params.set("family", filters.family);
    if (filters?.difficulty) params.set("difficulty", filters.difficulty);
    if (filters?.duration) params.set("duration", String(filters.duration));
    if (filters?.tag) params.set("tag", filters.tag);
    const qs = params.toString();
    return apiFetch<ScenarioOut[]>(`/scenarios${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<ScenarioOut>(`/scenarios/${id}`),
};

export const personas = {
  list: () => apiFetch<PersonaOut[]>("/personas"),
};

export const rubrics = {
  list: () => apiFetch<RubricOut[]>("/rubrics"),
  get: (id: string) => apiFetch<RubricOut>(`/rubrics/${id}`),
};

export interface CreateSessionBody {
  scenario_id: string;
  difficulty: Difficulty;
  target_minutes: 5 | 10 | 20 | 30;
  focus_areas?: string[];
  resume_text_override?: string | null;
}

export const sessions = {
  create: (body: CreateSessionBody) => apiFetch<SessionOut>("/sessions", { method: "POST", body }),
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const s = qs.toString();
    return apiFetch<Page<SessionOut>>(`/sessions${s ? `?${s}` : ""}`);
  },
  get: (id: string) => apiFetch<SessionOut>(`/sessions/${id}`),
  mintWsToken: (id: string) => apiFetch<WsTokenOut>(`/sessions/${id}/ws-token`, { method: "POST" }),
  mintReplayToken: (id: string) =>
    apiFetch<ReplayTokenOut>(`/sessions/${id}/replay-token`, { method: "POST" }),
  getReport: (id: string) => apiFetch<ReportOut>(`/sessions/${id}/report`),
  getTurns: (id: string) => apiFetch<TurnOut[]>(`/sessions/${id}/turns`),
  getScores: (id: string) => apiFetch<SessionScoreOut[]>(`/sessions/${id}/scores`),
  getRecording: (id: string) => apiFetch<RecordingOut>(`/sessions/${id}/recording`),
  annotate: (id: string, body: { turn_id: string; criterion_key: string; score: number; notes?: string | null }) =>
    apiFetch<AnnotationOut>(`/sessions/${id}/annotations`, { method: "POST", body }),
  retry: (id: string, body: { turn_id: string }) =>
    apiFetch<SessionOut>(`/sessions/${id}/retry`, { method: "POST", body }),
};
