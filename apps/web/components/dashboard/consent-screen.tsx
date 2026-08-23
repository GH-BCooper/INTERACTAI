"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

export interface ConsentDecision {
  recordingConsent: boolean;
  trainingConsent: boolean;
}

/**
 * Task 4.5a: "A consent record per session: recording_consent and training_consent as two
 * separate booleans... The recruited-session flow presents the consent screen before the audio
 * check." Both are explicit, independent choices — training consent is never pre-checked or
 * implied by agreeing to recording.
 */
export function ConsentScreen({
  onDecide,
  onCancel,
}: {
  onDecide: (decision: ConsentDecision) => void;
  onCancel: () => void;
}) {
  const [recordingConsent, setRecordingConsent] = useState(false);
  const [trainingConsent, setTrainingConsent] = useState(false);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="consent-title"
    >
      <div className="w-full max-w-md rounded-lg border bg-[var(--bg-card)] p-5">
        <h2 id="consent-title" className="text-md font-medium">
          Before we start
        </h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          This session is being run as part of a usability study. Please read and confirm both
          of the following separately — agreeing to one does not imply the other.
        </p>

        <label className="mt-4 flex items-start gap-3 rounded-lg border p-3 text-sm">
          <input
            type="checkbox"
            checked={recordingConsent}
            onChange={(e) => setRecordingConsent(e.target.checked)}
            className="mt-0.5 shrink-0"
          />
          <span>
            <span className="font-medium">I consent to being recorded.</span>
            <span className="mt-1 block text-xs text-[var(--text-secondary)]">
              Your audio and the transcript will be stored so the session can be scored and
              reviewed. Recordings are subject to your account&apos;s retention setting.
            </span>
          </span>
        </label>

        <label className="mt-3 flex items-start gap-3 rounded-lg border p-3 text-sm">
          <input
            type="checkbox"
            checked={trainingConsent}
            onChange={(e) => setTrainingConsent(e.target.checked)}
            className="mt-0.5 shrink-0"
          />
          <span>
            <span className="font-medium">I consent to my (de-identified) turns being used to improve scoring.</span>
            <span className="mt-1 block text-xs text-[var(--text-secondary)]">
              Optional, and separate from the recording consent above. You can revoke this at
              any time in Settings — revoking excludes your turns from any future training data
              build.
            </span>
          </span>
        </label>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!recordingConsent}
            onClick={() => onDecide({ recordingConsent, trainingConsent })}
          >
            Continue
          </Button>
        </div>
      </div>
    </div>
  );
}
