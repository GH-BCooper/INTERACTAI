"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/field";
import { capitalize } from "@/components/ui/primitives";
import { Segmented } from "@/components/ui/segmented";
import { Checkbox } from "@/components/ui/switch";
import { ApiError } from "@/lib/api/client";
import { useCreateSession, useMe, usePersonas } from "@/lib/api/hooks";
import type { Difficulty, ScenarioOut, TargetMinutes } from "@/lib/api/types";

import { ConsentScreen, type ConsentDecision } from "./consent-screen";
import { VoicePreviewButton } from "./voice-preview-button";

const DIFFICULTIES: Difficulty[] = ["gentle", "standard", "hard"];
const DURATIONS: TargetMinutes[] = [5, 10, 20, 30];

function nearestDuration(minutes: number): TargetMinutes {
  return DURATIONS.reduce((best, d) => (Math.abs(d - minutes) < Math.abs(best - minutes) ? d : best));
}

function firstSentence(text: string): string {
  const match = text.match(/^.*?[.!?](\s|$)/);
  return (match ? match[0] : text).trim();
}

/** The moment of commitment (docs/ui-audit-2026-09.md §6): who you will talk to, what it is
 * about, and two segmented choices. The research-consent path is admin-only — it exists for
 * recruited usability sessions, which an admin runs, not for everyday practice. */
export function StartSessionDialog({
  open = true,
  scenario,
  onClose,
  defaultMinutes,
}: {
  open?: boolean;
  scenario: ScenarioOut;
  onClose: () => void;
  defaultMinutes?: TargetMinutes;
}) {
  const [difficulty, setDifficulty] = useState<Difficulty>(scenario.difficulty);
  const [targetMinutes, setTargetMinutes] = useState<TargetMinutes>(
    defaultMinutes ?? nearestDuration(scenario.duration_minutes),
  );
  // Task 4.5a: "The recruited-session flow presents the consent screen before the audio
  // check." An ordinary personal-practice session skips this entirely and falls back to the
  // account's own Settings > Privacy default (services/api/app/services/session_service.py).
  const [isRecruitedSession, setIsRecruitedSession] = useState(false);
  const [showConsent, setShowConsent] = useState(false);
  const createSession = useCreateSession();
  const router = useRouter();
  const { data: me } = useMe();
  const { data: personas } = usePersonas();
  const persona = personas?.find((p) => p.id === scenario.persona_id) ?? null;

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

  const errorMessage =
    createSession.error instanceof ApiError
      ? createSession.error.message
      : createSession.error
        ? "Something went wrong starting this session."
        : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      labelledBy={showConsent ? "consent-title" : "start-session-title"}
      className="max-w-md p-5"
    >
      {showConsent ? (
        <ConsentScreen
          onCancel={() => setShowConsent(false)}
          onDecide={(decision) => {
            setShowConsent(false);
            void begin(decision);
          }}
        />
      ) : (
        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{capitalize(scenario.family)}</p>
          <h2 id="start-session-title" className="mt-1 text-md font-medium">
            {scenario.title}
          </h2>
          <p className="mt-1 line-clamp-2 text-sm text-[var(--text-secondary)]">{firstSentence(scenario.brief)}</p>

          {persona && (
            <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border bg-[var(--bg-page)] p-3">
              <div className="flex min-w-0 items-center gap-3">
                <span
                  aria-hidden
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-[var(--accent)] text-sm font-medium"
                >
                  {persona.name.charAt(0)}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{persona.name}</p>
                  <p className="truncate text-xs text-[var(--text-tertiary)]">
                    {capitalize(persona.archetype)} · {capitalize(persona.temperament)}
                  </p>
                </div>
              </div>
              <VoicePreviewButton personaId={persona.id} />
            </div>
          )}

          <Label className="mt-5">Difficulty</Label>
          <Segmented
            className="mt-1.5"
            variant="segmented"
            size="md"
            label="Difficulty"
            value={difficulty}
            onChange={setDifficulty}
            options={DIFFICULTIES.map((d) => ({ value: d, label: capitalize(d) }))}
          />

          <Label className="mt-4">Length</Label>
          <Segmented
            className="mt-1.5"
            variant="segmented"
            size="md"
            label="Length"
            value={targetMinutes}
            onChange={setTargetMinutes}
            options={DURATIONS.map((d) => ({ value: d, label: `${d} min` }))}
          />

          {me?.user.is_admin && (
            <Checkbox
              checked={isRecruitedSession}
              onChange={setIsRecruitedSession}
              className="mt-4 text-xs text-[var(--text-secondary)]"
            >
              Recruited/research session (shows a consent screen first) · admin
            </Checkbox>
          )}

          {errorMessage && (
            <p role="alert" className="mt-3 text-xs text-[var(--status-bad)]">
              {errorMessage}
              {createSession.error instanceof ApiError && createSession.error.recovery
                ? ` ${createSession.error.recovery}`
                : ""}
            </p>
          )}

          <div className="mt-6 flex items-center justify-between gap-2">
            <p className="text-xs text-[var(--text-tertiary)]">You&apos;ll check your mic before it starts.</p>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={onBeginClicked} disabled={createSession.isPending} data-autofocus>
                {createSession.isPending ? "Starting…" : "Begin session"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Dialog>
  );
}
