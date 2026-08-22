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
}

export interface ProfileOut {
  id: string;
  resume_text: string | null;
  resume_updated_at: string | null;
  target_role: string | null;
}

export interface MeOut {
  user: UserOut;
  profile: ProfileOut | null;
  practice_minutes_this_week: number;
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
