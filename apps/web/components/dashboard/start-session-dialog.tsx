"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useCreateSession } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/client";
import type { Difficulty, ScenarioOut, TargetMinutes } from "@/lib/api/types";
import { Button } from "@/components/ui/button";

import { ConsentScreen, type ConsentDecision } from "./consent-screen";

const DIFFICULTIES: Difficulty[] = ["gentle", "standard", "hard"];
const DURATIONS: TargetMinutes[] = [5, 10, 20, 30];

function nearestDuration(minutes: number): TargetMinutes {
  return DURATIONS.reduce((best, d) => (Math.abs(d - minutes) < Math.abs(best - minutes) ? d : best));
}

export function StartSessionDialog({
  scenario,
  onClose,
}: {
  scenario: ScenarioOut;
  onClose: () => void;
}) {
  const [difficulty, setDifficulty] = useState<Difficulty>(scenario.difficulty);
  const [targetMinutes, setTargetMinutes] = useState<TargetMinutes>(
    nearestDuration(scenario.duration_minutes),
  );
  // Task 4.5a: "The recruited-session flow presents the consent screen before the audio
  // check." An ordinary personal-practice session skips this entirely and falls back to the
  // account's own Settings > Privacy default (services/api/app/services/session_service.py).
  const [isRecruitedSession, setIsRecruitedSession] = useState(false);
  const [showConsent, setShowConsent] = useState(false);
  const createSession = useCreateSession();
  const router = useRouter();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function begin(consent?: ConsentDecision) {
    try {
      const session = await createSession.mutateAsync({
        scenario_id: scenario.id,
        difficulty,
        target_minutes: targetMinutes,
        ...(consent
          ? { recording_consent: consent.recordingConsent, training_consent: consent.trainingConsent }
          : {}),
      });
      router.push(`/app/practice/${session.id}`);
    } catch {
      // Surfaced via createSession.error below.
    }
  }

  function onBeginClicked() {
    if (isRecruitedSession) {
      setShowConsent(true);
      return;
    }
    void begin();
  }

  if (showConsent) {
    return (
      <ConsentScreen
        onCancel={() => setShowConsent(false)}
        onDecide={(decision) => {
          setShowConsent(false);
          void begin(decision);
        }}
      />
    );
  }

  const errorMessage =
    createSession.error instanceof ApiError
      ? createSession.error.message
      : createSession.error
        ? "Something went wrong starting this session."
        : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="start-session-title"
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-[var(--bg-card)] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="start-session-title" className="text-md font-medium">
          {scenario.title}
        </h2>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">
          {scenario.family} · {scenario.duration_minutes} min authored length
        </p>

        <label className="mt-4 block text-xs text-[var(--text-secondary)]" htmlFor="difficulty-select">
          Difficulty
        </label>
        <select
          id="difficulty-select"
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value as Difficulty)}
          className="mt-1 w-full rounded-md border bg-[var(--bg-page)] px-3 py-2 text-sm"
        >
          {DIFFICULTIES.map((d) => (
            <option key={d} value={d}>
              {d[0]!.toUpperCase() + d.slice(1)}
            </option>
          ))}
        </select>

        <label className="mt-3 block text-xs text-[var(--text-secondary)]" htmlFor="duration-select">
          Duration
        </label>
        <select
          id="duration-select"
          value={targetMinutes}
          onChange={(e) => setTargetMinutes(Number(e.target.value) as TargetMinutes)}
          className="mt-1 w-full rounded-md border bg-[var(--bg-page)] px-3 py-2 text-sm"
        >
          {DURATIONS.map((d) => (
            <option key={d} value={d}>
              {d} minutes
            </option>
          ))}
        </select>

        <label className="mt-4 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={isRecruitedSession}
            onChange={(e) => setIsRecruitedSession(e.target.checked)}
          />
          This is a recruited/research session (shows a consent screen first)
        </label>

        {errorMessage && (
          <p role="alert" className="mt-3 text-xs text-[var(--danger)]">
            {errorMessage}
            {createSession.error instanceof ApiError && createSession.error.recovery
              ? ` ${createSession.error.recovery}`
              : ""}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={onBeginClicked} disabled={createSession.isPending}>
            {createSession.isPending ? "Starting…" : "Begin session"}
          </Button>
        </div>
      </div>
    </div>
  );
}
