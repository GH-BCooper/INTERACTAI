"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

/** Task 3.2 non-negotiable #5: "Escape does not end the session. Ending requires a confirmed
 * action." Escape here only cancels *this dialog* — never a shortcut for the destructive action
 * itself, matching CLAUDE.md's general "hard-to-reverse operations get confirmation" stance. */
export function EndSessionDialog({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="end-session-title"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-[var(--bg-card)] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="end-session-title" className="text-md font-medium">
          End this session?
        </h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Your recording so far is already saved. Ending now stops the conversation and starts
          scoring.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} autoFocus>
            Keep talking
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>
            End session
          </Button>
        </div>
      </div>
    </div>
  );
}
