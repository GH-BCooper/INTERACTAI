import { apiFetch } from "./client";
import type {
  AnnotationOut,
  AnnotationProgress,
  AnnotationQueueItem,
  AnnotationSubmitOut,
  CompareOut,
  CostPanelOut,
  DashboardOut,
  Difficulty,
  EvalCaseRow,
  EvalRunRow,
  LatencyHeaderOut,
  MeOut,
  ModelCallPage,
  ModelVersionRow,
  ModelsSettingsOut,
  ObservedTurn,
  Page,
  PersonaOut,
  PrivacySettingsOut,
  ProgressOut,
  ProviderConnectionTestOut,
  ProviderCredentialOut,
  ProviderName,
  RegressionOut,
  RecordingOut,
  ReplayTokenOut,
  ReportOut,
  RubricOut,
  ScenarioOut,
  ScenarioProgressOut,
  SessionOut,
  SessionScoreOut,
  StageRow,
  TurnOut,
  UserDataExport,
  UserOut,
  VoicePreviewTokenOut,
  WaterfallOut,
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

// docs/phase-5-BUILD.md TASK 5.3 — the admin-only annotation tool. Separate from
// `sessions.annotate` above (Task 3.4e's self-serve, per-session control): this queue spans
// every session, shows anchor descriptors, audio and (train-split-only) pre-labels.
export const adminAnnotate = {
  getQueue: (params?: { limit?: number; preLabelled?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.preLabelled) qs.set("pre_labelled", "true");
    const s = qs.toString();
    return apiFetch<AnnotationQueueItem[]>(`/admin/annotate/queue${s ? `?${s}` : ""}`);
  },
  submit: (body: {
    turn_id: string;
    criterion_key: string;
    score: number;
    notes?: string | null;
    pre_label_score?: number | null;
  }) => apiFetch<AnnotationSubmitOut>("/admin/annotate/submit", { method: "POST", body }),
  getProgress: () => apiFetch<AnnotationProgress>("/admin/annotate/progress"),
};

// Phase 6 TASK 6.1/6.2 — admin observability and evaluations. Promotion/rollback go through the
// existing /admin/registry/* routes (Task 5.5c) — status changes only.
function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export interface LatencyFilter {
  days: number;
  family?: string;
  host_class?: string;
}

export interface ModelCallFilter {
  role?: string;
  model?: string;
  cached?: boolean;
  sort?: string;
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export const adminObservability = {
  latency: (f: LatencyFilter) => apiFetch<LatencyHeaderOut>(`/admin/observability/latency${qs({ ...f })}`),
  stages: (f: LatencyFilter) => apiFetch<StageRow[]>(`/admin/observability/stages${qs({ ...f })}`),
  turns: () => apiFetch<ObservedTurn[]>("/admin/observability/turns"),
  waterfall: (turnId: string) => apiFetch<WaterfallOut>(`/admin/observability/turns/${turnId}`),
  replayToken: (sessionId: string) =>
    apiFetch<ReplayTokenOut>(`/admin/observability/sessions/${sessionId}/replay-token`, { method: "POST" }),
  recording: (sessionId: string) =>
    apiFetch<RecordingOut>(`/admin/observability/sessions/${sessionId}/recording`),
  modelCalls: (f: ModelCallFilter) => apiFetch<ModelCallPage>(`/admin/observability/model-calls${qs({ ...f })}`),
  cost: () => apiFetch<CostPanelOut>("/admin/observability/cost"),
};

export const adminEvals = {
  versions: () => apiFetch<ModelVersionRow[]>("/admin/evals/versions"),
  runs: (suite?: string) => apiFetch<EvalRunRow[]>(`/admin/evals/runs${qs({ suite })}`),
  regression: () => apiFetch<RegressionOut>("/admin/evals/regression"),
  cases: (modelVersion?: string) => apiFetch<{ items: EvalCaseRow[] }>(`/admin/evals/cases${qs({ model_version: modelVersion })}`),
  scoreVersions: () => apiFetch<string[]>("/admin/evals/score-versions"),
  compare: (a: string, b: string) => apiFetch<CompareOut>(`/admin/evals/compare${qs({ version_a: a, version_b: b })}`),
  speech: () => apiFetch<EvalRunRow[]>("/admin/evals/speech"),
  promote: (candidateVersionId: string) =>
    apiFetch<unknown>("/admin/registry/promote", { method: "POST", body: { candidate_version_id: candidateVersionId } }),
  rollback: (targetVersionId: string) =>
    apiFetch<unknown>("/admin/registry/rollback", { method: "POST", body: { target_version_id: targetVersionId } }),
};
