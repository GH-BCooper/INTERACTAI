"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  adminAnnotate,
  me,
  personas,
  rubrics,
  scenarios,
  sessions,
  type CreateSessionBody,
  type ProfileUpdateBody,
} from "./resources";
import type { ProviderName } from "./types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: me.get });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileUpdateBody) => me.updateProfile(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useCompleteOnboarding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: me.completeOnboarding,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function usePrivacySettings() {
  return useQuery({ queryKey: ["me", "privacy"], queryFn: me.getPrivacy });
}

export function useUpdatePrivacySettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: me.updatePrivacy,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me", "privacy"] }),
  });
}

export function useModelsSettings() {
  return useQuery({ queryKey: ["me", "models"], queryFn: me.getModels });
}

export function useUpdateModelsSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: me.updateModels,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me", "models"] }),
  });
}

export function useProviders() {
  return useQuery({ queryKey: ["me", "providers"], queryFn: me.listProviders });
}

export function useSaveProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, apiKey }: { provider: ProviderName; apiKey: string }) =>
      me.saveProvider(provider, apiKey),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me", "providers"] }),
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: ProviderName) => me.deleteProvider(provider),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me", "providers"] }),
  });
}

export function useTestProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: ProviderName) => me.testProvider(provider),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me", "providers"] }),
  });
}

export function useExportMyData() {
  return useMutation({ mutationFn: me.export });
}

export function useDashboard() {
  return useQuery({ queryKey: ["me", "dashboard"], queryFn: me.dashboard });
}

export function useProgress(family?: string) {
  return useQuery({
    queryKey: ["me", "progress", family ?? null],
    queryFn: () => me.progress(family),
  });
}

export function useScenarioProgress() {
  return useQuery({ queryKey: ["me", "scenario-progress"], queryFn: me.scenarioProgress });
}

export function useScenarios(filters?: {
  family?: string;
  difficulty?: string;
  duration?: number;
  tag?: string;
}) {
  return useQuery({
    queryKey: ["scenarios", filters ?? {}],
    queryFn: () => scenarios.list(filters),
  });
}

export function useDeleteMe() {
  return useMutation({ mutationFn: me.delete });
}

export function useScenario(id: string | undefined) {
  return useQuery({
    queryKey: ["scenarios", id],
    queryFn: () => scenarios.get(id as string),
    enabled: !!id,
  });
}

export function usePersonas() {
  return useQuery({ queryKey: ["personas"], queryFn: personas.list });
}

export function useRubric(id: string | null | undefined) {
  return useQuery({
    queryKey: ["rubrics", id],
    queryFn: () => rubrics.get(id as string),
    enabled: !!id,
  });
}

export function useSessions(params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["sessions", params ?? {}],
    queryFn: () => sessions.list(params),
  });
}

export function useSession(id: string | undefined) {
  return useQuery({
    queryKey: ["sessions", id],
    queryFn: () => sessions.get(id as string),
    enabled: !!id,
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateSessionBody) => sessions.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useSessionReport(id: string | undefined, options?: { pollWhilePending?: boolean }) {
  return useQuery({
    queryKey: ["sessions", id, "report"],
    queryFn: () => sessions.getReport(id as string),
    enabled: !!id,
    retry: (failureCount, error) => {
      // A 404 here means "not generated yet", not a real error — TASK 3.3g: the report keeps
      // polling until the coach job finishes rather than surfacing a permanent failure.
      const status = (error as { status?: number }).status;
      return status === 404 && failureCount < 1000;
    },
    refetchInterval: (query) => {
      if (!options?.pollWhilePending) return false;
      const data = query.state.data;
      if (data && data.status !== "pending") return false;
      return 4000;
    },
  });
}

export function useSessionTurns(id: string | undefined) {
  return useQuery({
    queryKey: ["sessions", id, "turns"],
    queryFn: () => sessions.getTurns(id as string),
    enabled: !!id,
  });
}

export function useSessionScores(id: string | undefined) {
  return useQuery({
    queryKey: ["sessions", id, "scores"],
    queryFn: () => sessions.getScores(id as string),
    enabled: !!id,
  });
}

export function useSessionRecording(id: string | undefined) {
  return useQuery({
    queryKey: ["sessions", id, "recording"],
    queryFn: () => sessions.getRecording(id as string),
    enabled: !!id,
  });
}

export function useAnnotate(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { turn_id: string; criterion_key: string; score: number; notes?: string | null }) =>
      sessions.annotate(sessionId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions", sessionId, "turns"] }),
  });
}

export function useRetryQuestion(sessionId: string) {
  return useMutation({
    mutationFn: (turnId: string) => sessions.retry(sessionId, { turn_id: turnId }),
  });
}

// docs/phase-5-BUILD.md TASK 5.3 — admin annotation tool.
export function useAdminAnnotationQueue(params?: { limit?: number; preLabelled?: boolean }) {
  return useQuery({
    queryKey: ["admin-annotate", "queue", params?.limit, params?.preLabelled],
    queryFn: () => adminAnnotate.getQueue(params),
  });
}

export function useAdminAnnotationProgress() {
  return useQuery({
    queryKey: ["admin-annotate", "progress"],
    queryFn: () => adminAnnotate.getProgress(),
  });
}

export function useAdminAnnotationSubmit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: adminAnnotate.submit,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-annotate"] });
    },
  });
}
