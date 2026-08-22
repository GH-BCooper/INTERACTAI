"use client";

import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { detectBrowser } from "@/lib/browser-detect";
import type { MicPermissionState } from "@/hooks/use-audio-capture";

const RECOVERY_STEPS: Record<Exclude<ReturnType<typeof detectBrowser>, "other">, string[]> = {
  chrome: [
    "Click the padlock (or camera/mic icon) at the left of the address bar.",
    'Set "Microphone" to Allow.',
    "Reload this page.",
  ],
  firefox: [
    'Click the microphone icon with a line through it in the address bar, or open Settings → Privacy & Security → Permissions → Microphone.',
    "Remove the block for this site, or allow it.",
    "Reload this page.",
  ],
  safari: [
    "Open Safari → Settings for This Website (or Safari → Settings → Websites → Microphone).",
    'Set this site to "Allow".',
    "On macOS, also check System Settings → Privacy & Security → Microphone includes Safari.",
    "Reload this page.",
  ],
};

const GENERIC_STEPS = [
  "Open your browser's site settings for this page.",
  "Allow microphone access.",
  "Reload this page.",
];

interface MicPermissionErrorProps {
  state: Extract<MicPermissionState, "denied" | "no_device" | "revoked" | "error">;
  onRetry: () => void;
}

/** Task 3.2 edge case: "Mic permission denied -> Browser-specific recovery instructions
 * (Chrome / Firefox / Safari differ, and macOS adds an OS layer). Not a generic message." */
export function MicPermissionError({ state, onRetry }: MicPermissionErrorProps) {
  const browser = useMemo(
    () => detectBrowser(typeof navigator === "undefined" ? "" : navigator.userAgent),
    [],
  );
  const steps = browser === "other" ? GENERIC_STEPS : RECOVERY_STEPS[browser];

  const heading =
    state === "no_device"
      ? "No microphone was found"
      : state === "revoked"
        ? "Microphone access was interrupted"
        : "Microphone access is blocked";

  const body =
    state === "no_device"
      ? "Connect a microphone or headset, then try again."
      : "InteractAI needs your microphone to hear you speak. This is only used for this practice session.";

  return (
    <div className="mx-auto max-w-sm rounded-lg border bg-[var(--bg-card)] p-6 text-center">
      <p className="text-md font-medium">{heading}</p>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">{body}</p>
      {state !== "no_device" && (
        <ol className="mt-4 list-inside list-decimal space-y-1 text-left text-xs text-[var(--text-tertiary)]">
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}
      <Button variant="primary" size="sm" className="mt-5" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}
