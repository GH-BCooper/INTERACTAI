import { apiFetch } from "./client";
import type {
  AnnotationOut,
  DashboardOut,
  Difficulty,
  MeOut,
  ModelsSettingsOut,
  Page,
  PersonaOut,
  PrivacySettingsOut,
  ProgressOut,
  ProviderConnectionTestOut,
  ProviderCredentialOut,
  ProviderName,
  RecordingOut,
  ReplayTokenOut,
  ReportOut,
  RubricOut,
  ScenarioOut,
  ScenarioProgressOut,
  SessionOut,
  SessionScoreOut,
  TurnOut,
  UserDataExport,
  UserOut,
  VoicePreviewTokenOut,
  WsTokenOut,
} from "./types";

export interface ProfileUpdateBody {
  resume_text?: string | null;
  target_role?: string | null;
  clear_resume?: boolean;
  goal?: string | null;
  experience_level?: string | null;
  focus_areas?: string[];
  captions_default?: boolean;
  speaking_rate?: number;
  noise_suppression?: boolean;
  echo_cancellation?: boolean;
}

export const me = {
  get: () => apiFetch<MeOut>("/me"),
  updateProfile: (body: ProfileUpdateBody) =>
    apiFetch<MeOut["profile"]>("/me/profile", { method: "PATCH", body }),
  completeOnboarding: () => apiFetch<UserOut>("/me/onboarding/complete", { method: "POST" }),
  getPrivacy: () => apiFetch<PrivacySettingsOut>("/me/privacy"),
  updatePrivacy: (body: { training_consent?: boolean; audio_retention_days?: number }) =>
    apiFetch<PrivacySettingsOut>("/me/privacy", { method: "PATCH", body }),
  getModels: () => apiFetch<ModelsSettingsOut>("/me/models"),
  updateModels: (body: { prefer_local_models?: boolean }) =>
    apiFetch<ModelsSettingsOut>("/me/models", { method: "PATCH", body }),
  listProviders: () => apiFetch<ProviderCredentialOut[]>("/me/providers"),
  saveProvider: (provider: ProviderName, apiKey: string) =>
    apiFetch<ProviderCredentialOut>(`/me/providers/${provider}`, {
      method: "PUT",
      body: { api_key: apiKey },
    }),
  deleteProvider: (provider: ProviderName) =>
    apiFetch<void>(`/me/providers/${provider}`, { method: "DELETE" }),
  testProvider: (provider: ProviderName) =>
    apiFetch<ProviderConnectionTestOut>(`/me/providers/${provider}/test`, { method: "POST" }),
  export: () => apiFetch<UserDataExport>("/me/export"),
  dashboard: () => apiFetch<DashboardOut>("/me/dashboard"),
  progress: (family?: string) =>
    apiFetch<ProgressOut>(`/me/progress${family ? `?family=${encodeURIComponent(family)}` : ""}`),
  scenarioProgress: () => apiFetch<Record<string, ScenarioProgressOut>>("/me/scenario-progress"),
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
  mintVoicePreviewToken: (id: string) =>
    apiFetch<VoicePreviewTokenOut>(`/personas/${id}/voice-preview-token`, { method: "POST" }),
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
  // Task 4.5a — only the recruited-session consent screen sends these explicitly; an ordinary
  // session omits them and the account's own Settings > Privacy default applies server-side.
  recording_consent?: boolean;
  training_consent?: boolean;
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
