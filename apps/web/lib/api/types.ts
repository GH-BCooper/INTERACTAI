/**
 * Hand-mirrored from services/api/app/schemas/*.py — api and web are independent workspace
 * members (the same principle as docs/decisions/0003, applied to the api/web boundary): there
 * is no shared schema package for REST like there is for the WS protocol
 * (packages/schema/ws-messages.schema.json). Field names and shapes must stay in sync by hand;
 * the integration tests in tests/integration exercise the real JSON these are validated against.
 */

export type Difficulty = "gentle" | "standard" | "hard";
export type TargetMinutes = 5 | 10 | 20 | 30;

export interface UserOut {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  created_at: string;
  onboarded_at: string | null;
  is_admin: boolean;
}

export interface AnnotationQueueItem {
  turn_id: string;
  session_id: string;
  question: string;
  answer_text: string;
  answer_is_scrubbed: boolean;
  audio_url: string | null;
  audio_start_ms: number;
  audio_end_ms: number;
  criterion_key: string;
  criterion_name: string;
  anchor_descriptors: Record<string, string>;
  split: string;
  double_labeled: boolean;
  pre_label_score: number | null;
}

export interface AnnotationSubmitOut {
  id: string;
  turn_id: string;
  criterion_key: string;
  round: number;
  score: number;
  created_at: string;
}

export interface AnnotationProgress {
  dataset_revision_hash: string | null;
  total_candidate_pairs: number;
  labeled_pairs: number;
  double_labeled_target: number;
  double_labeled_with_two_annotators: number;
  disagreements_pending_adjudication: number;
}

export type Goal = "job_interview" | "technical_interview" | "salary_negotiation";
export type ExperienceLevel = "student" | "early_career" | "mid_level" | "senior" | "staff_plus";

export interface ProfileOut {
  id: string;
  resume_text: string | null;
  resume_updated_at: string | null;
  target_role: string | null;
  goal: Goal | null;
  experience_level: ExperienceLevel | null;
  focus_areas: string[];
  captions_default: boolean;
  speaking_rate: number;
  noise_suppression: boolean;
  echo_cancellation: boolean;
}

export interface PrivacySettingsOut {
  training_consent: boolean;
  audio_retention_days: number;
}

export interface ModelsSettingsOut {
  prefer_local_models: boolean;
}

export type ProviderName = "groq";
export type ConnectionTestStatus = "untested" | "success" | "failed";

export interface ProviderCredentialOut {
  provider: ProviderName;
  has_key: boolean;
  last_test_status: ConnectionTestStatus;
  last_tested_at: string | null;
}

export interface ProviderConnectionTestOut {
  provider: ProviderName;
  success: boolean;
  message: string;
  tested_at: string;
}

export interface MeOut {
  user: UserOut;
  profile: ProfileOut | null;
  practice_minutes_this_week: number;
}

export interface VoicePreviewTokenOut {
  token: string;
  expires_in: number;
  voice_id: string;
}

export interface PersonaOut {
  id: string;
  slug: string;
  name: string;
  archetype: string;
  temperament: string;
  voice_id: string;
  brief: string;
}

export interface ScenarioOut {
  id: string;
  slug: string;
  family: string;
  difficulty: Difficulty;
  title: string;
  brief: string;
  opening_strategy: string;
  duration_minutes: number;
  tags: string[];
  persona_id: string | null;
  rubric_id: string | null;
}

export interface RubricCriterionOut {
  id: string;
  key: string;
  name: string;
  description: string;
  display_order: number;
  anchor_descriptors: Record<string, string>;
}

export interface RubricOut {
  id: string;
  slug: string;
  name: string;
  description: string;
  criteria: RubricCriterionOut[];
}

export type SessionStatus = "created" | "active" | "closing" | "closed" | "failed";

export interface SessionOut {
  id: string;
  scenario_id: string;
  status: SessionStatus;
  end_reason: string | null;
  target_minutes: number;
  focus_areas: string[];
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  created_at: string;
  recording_available: boolean;
  retry_of_session_id: string | null;
  retry_of_turn_id: string | null;
}

export interface WsTokenOut {
  token: string;
  expires_in: number;
  ws_url: string;
}

export interface ReplayTokenOut {
  token: string;
  expires_in: number;
}

export interface RecordingOut {
  url: string | null;
  format: "wav" | "opus" | null;
  peaks: number[] | null;
  duration_ms: number | null;
}

export interface NextActionOut {
  text: string;
  turn_id: string | null;
}

export type ReportStatus = "pending" | "ready" | "failed";

export interface ReportOut {
  id: string;
  session_id: string;
  status: ReportStatus;
  summary: string | null;
  strengths: string[];
  growth_areas: string[];
  next_actions: NextActionOut[];
  highlight_turn_id: string | null;
  lowlight_turn_id: string | null;
  low_sample_size: boolean;
  generated_at: string | null;
}

export interface WordTimingOut {
  word: string;
  start_ms: number;
  end_ms: number;
}

export interface TurnScoreOut {
  criterion_key: string;
  score: number | null;
  confidence: number;
  evidence_spans: { start: number; end: number }[];
  model_version: string;
}

export interface TurnMetricsOut {
  wpm: number;
  filler_count: number;
  filler_rate: number;
  longest_pause_ms: number;
  speech_ratio: number;
  word_count: number;
}

export type Speaker = "user" | "persona";

export interface TurnOut {
  id: string;
  index: number;
  speaker: Speaker;
  text: string;
  text_scrubbed: string | null;
  start_ms: number;
  end_ms: number;
  word_timings: WordTimingOut[];
  truncated: boolean;
  asr_confidence: number | null;
  metrics: TurnMetricsOut | null;
  scores: TurnScoreOut[];
}

export interface SessionScoreOut {
  criterion_key: string;
  name: string;
  aggregate_score: number | null;
  confidence: number;
  percentile_vs_self: number | null;
  evidence_turn_ids: string[];
  anchor_descriptors: Record<string, string>;
}

export interface AnnotationOut {
  id: string;
  turn_id: string;
  criterion_key: string;
  round: number;
  score: number;
  notes: string | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// ── Task 4.1/4.4 — dashboard, recommendation, progress ──────────────────────────────────────

export type RecommendationKind = "continue_session" | "start_scenario";

export interface RecommendationOut {
  kind: RecommendationKind;
  reason: string;
  session_id: string | null;
  scenario_id: string | null;
}

export interface ProgressStripOut {
  sessions_this_week: number;
  total_minutes_this_week: number;
  overall_score: number | null;
  overall_score_delta: number | null;
  weakest_criterion_name: string | null;
}

export interface RecentSessionOut {
  id: string;
  scenario_title: string;
  created_at: string;
  duration_ms: number | null;
  overall_score: number | null;
  report_read: boolean;
}

export type AttentionKind = "unread_report" | "stalled_scenario" | "declining_criterion";

export interface AttentionItemOut {
  kind: AttentionKind;
  text: string;
  session_id: string | null;
  scenario_id: string | null;
}

export interface DashboardOut {
  recommendation: RecommendationOut;
  progress_strip: ProgressStripOut;
  recent_sessions: RecentSessionOut[];
  attention: AttentionItemOut | null;
}

export interface ScenarioAttemptOut {
  session_id: string;
  created_at: string;
  overall_score: number | null;
}

export interface ScenarioProgressOut {
  attempts: number;
  best_score: number | null;
  recent_attempts: ScenarioAttemptOut[];
}

export interface CriterionTrendPointOut {
  session_id: string;
  created_at: string;
  score: number;
}

export interface CriterionTrendOut {
  criterion_key: string;
  name: string;
  points: CriterionTrendPointOut[];
}

export interface WeeklyVolumePointOut {
  week_start: string;
  minutes: number;
  sessions: number;
}

export interface PersonalBestOut {
  criterion_key: string;
  name: string;
  score: number;
  session_id: string;
  achieved_at: string;
}

export interface WeakestDimensionOut {
  criterion_key: string;
  name: string;
  trend: number;
  next_action: string;
}

export interface ProgressOut {
  family: string;
  families_available: string[];
  criterion_trends: CriterionTrendOut[];
  weekly_volume: WeeklyVolumePointOut[];
  families_attempted: string[];
  families_never_attempted: string[];
  weakest_dimension: WeakestDimensionOut | null;
  personal_bests: PersonalBestOut[];
}

export interface UserDataExport {
  exported_at: string;
  user: { id: string; email: string; name: string | null; created_at: string };
  profile: {
    target_role: string | null;
    goal: string | null;
    experience_level: string | null;
    resume_text: string | null;
  } | null;
  sessions: Array<{
    id: string;
    scenario_id: string;
    status: string;
    created_at: string;
    started_at: string | null;
    ended_at: string | null;
    duration_ms: number | null;
    target_minutes: number;
    turns: TurnOut[];
  }>;
}

// ── Phase 6 TASK 6.1/6.2 — observability and evaluations (admin) ───────────────────────────

export interface PercentileRow {
  p50: number | null;
  p90: number | null;
  p95: number | null;
  n: number;
}

export interface LatencyHeaderOut {
  target_p95_ms: number;
  overall: PercentileRow;
  series: (PercentileRow & { bucket: string })[];
  families: string[];
  host_classes: string[];
}

export interface StageRow {
  stage: string;
  p50: number | null;
  p95: number | null;
  n: number;
}

export interface ObservedTurn {
  turn_id: string;
  session_id: string;
  e2e_ms: number;
  created_at: string;
}

export interface ModelCallOut {
  id: string;
  session_id: string;
  turn_id: string | null;
  role: string;
  model: string;
  prompt_version: string | null;
  tokens_in: number;
  tokens_out: number;
  ttft_ms: number | null;
  total_latency_ms: number;
  cost_cents: number;
  cached: boolean;
  created_at: string;
}

export interface ModelCallPage {
  items: ModelCallOut[];
  total: number;
  cache_hits: number;
  cache_misses: number;
}

export interface WaterfallOut {
  turn_id: string;
  session_id: string;
  e2e_ms: number | null;
  stages: { stage: string; duration_ms: number | null; model_calls: ModelCallOut[] }[];
  all_model_calls: ModelCallOut[];
  user_text: string | null;
  user_start_ms: number | null;
  user_end_ms: number | null;
  persona_turn_id: string | null;
  persona_text: string | null;
  persona_voice_id: string | null;
  recording_available: boolean;
}

export interface CostPanelOut {
  actual_total_cents: number;
  scoring_actual_cents: number;
  turn_scores: number;
  counterfactual_cents: number | null;
  ratio: number | null;
  frontier: { model: string; input_usd_per_mtok: number; output_usd_per_mtok: number; as_of: string };
  per_month: { month: string; cents: number }[];
  per_session: { session_id: string; cents: number }[];
  per_user: { user: string; cents: number }[];
}

export interface ModelVersionRow {
  id: string;
  role: string;
  name: string;
  base_model: string;
  adapter_key: string | null;
  dataset_revision_hash: string | null;
  metrics: Record<string, unknown>;
  status: "training" | "candidate" | "active" | "retired";
  seed_count: number;
  created_at: string;
}

export interface EvalRunRow {
  id: string;
  suite: string;
  configuration: string;
  model_version_id: string | null;
  prompt_version: string | null;
  qwk: number | null;
  mae: number | null;
  spearman: number | null;
  adjacent_accuracy: number | null;
  ece: number | null;
  mean_cost_cents: number | null;
  mean_latency_ms: number | null;
  metrics: Record<string, number | string | boolean | null>;
  host_class: string | null;
  dataset_revision_hash: string;
  split: string;
  published: boolean;
  created_at: string;
}

export interface RegressionOut {
  runs: EvalRunRow[];
  deployments: { id: string; kind: string; label: string; created_at: string }[];
}

export interface EvalCaseRow {
  session_id: string;
  turn_id: string;
  criterion_key: string;
  model_score: number;
  confidence: number;
  model_version: string;
  human_mean: number;
  human_scores: number[];
  disagreement: number;
  turn_text: string | null;
}

export interface CompareOut {
  version_a: string;
  version_b: string;
  shared_cases: number;
  disagreements: number;
  per_criterion: Record<string, { cases: number; disagreements: number }>;
  items: {
    turn_id: string;
    criterion_key: string;
    score_a: number | null;
    score_b: number | null;
    gap: number | null;
    disagrees: boolean;
  }[];
}
