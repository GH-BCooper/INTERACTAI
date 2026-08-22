"use client";

import { Circle, CircleCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { usePracticeStore } from "@/stores/practice-store";

const DISMISS_DELAY_MS = 2500;

function CheckRow({ done, children }: { done: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      {done ? (
        <CircleCheck size={14} className="mt-0.5 shrink-0 text-[var(--accent)]" />
      ) : (
        <Circle size={14} className="mt-0.5 shrink-0 text-[var(--text-tertiary)]" />
      )}
      <span>{children}</span>
    </li>
  );
}

/** Task 3.2 (AU-09): "Before the first session ever: a three-second 'say hello' test verifying
 * capture -> transport -> ASR -> playback end to end, with the transcript shown back." Rather
 * than a separate synthetic mode the backend doesn't have, this makes the *real* first exchange
 * legible as a confidence check: the scripted opening line (already spoken automatically,
 * Task 2.3f) is the playback proof, and the user's first reply streaming back as a live partial
 * transcript is the capture/transport/ASR proof — the same pipeline the rest of the session
 * uses, not a special case that could pass while the real thing is broken. */
export function PreflightOverlay({ onDismiss }: { onDismiss: () => void }) {
  const clientState = usePracticeStore((s) => s.clientState);
  const captionText = usePracticeStore((s) => s.captionText);
  const captionSpeaker = usePracticeStore((s) => s.captionSpeaker);
  const [heardPersona, setHeardPersona] = useState(false);
  const [heardUser, setHeardUser] = useState(false);
  const [transcriptSample, setTranscriptSample] = useState("");

  useEffect(() => {
    if (clientState === "speaking") setHeardPersona(true);
  }, [clientState]);

  useEffect(() => {
    if (captionSpeaker === "user" && captionText.trim().length > 0) {
      setHeardUser(true);
      setTranscriptSample(captionText);
    }
  }, [captionSpeaker, captionText]);

  useEffect(() => {
    if (!heardPersona || !heardUser) return;
    const timer = setTimeout(onDismiss, DISMISS_DELAY_MS);
    return () => clearTimeout(timer);
  }, [heardPersona, heardUser, onDismiss]);

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-[var(--bg-page)]/95 pt-20">
      <div className="max-w-sm rounded-lg border bg-[var(--bg-card)] p-5 text-sm shadow-none">
        <p className="font-medium">Checking your mic and speakers</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Listen for the persona, then say hello back.
        </p>
        <ul className="mt-4 space-y-2 text-xs">
          <CheckRow done={heardPersona}>Speaker check — you should hear the persona speak</CheckRow>
          <CheckRow done={heardUser}>
            Microphone check{transcriptSample ? ` — we heard: "${transcriptSample}"` : ""}
          </CheckRow>
        </ul>
        <button
          type="button"
          onClick={onDismiss}
          className="mt-4 text-xs text-[var(--text-tertiary)] underline hover:text-[var(--text-primary)]"
        >
          {heardPersona && heardUser ? "Continue" : "Skip this check"}
        </button>
      </div>
    </div>
  );
}
