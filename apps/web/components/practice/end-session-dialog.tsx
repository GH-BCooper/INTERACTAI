"use client";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

/** Task 3.2 non-negotiable #5: "Escape does not end the session. Ending requires a confirmed
 * action." Escape *opens* this dialog and, inside it, only cancels the dialog — never a shortcut
 * for the destructive action itself. "Keep talking" gets initial focus, so Enter is safe too. */
export function EndSessionDialog({
  open,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={open} onClose={onCancel} role="alertdialog" labelledBy="end-session-title" describedBy="end-session-body">
      <h2 id="end-session-title" className="text-md font-medium">
        End this session?
      </h2>
      <p id="end-session-body" className="mt-2 text-sm text-[var(--text-secondary)]">
        Your recording so far is already saved. Ending now stops the conversation and starts scoring.
      </p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel} data-autofocus>
          Keep talking
        </Button>
        <Button variant="danger" size="sm" onClick={onConfirm}>
          End session
        </Button>
      </div>
    </Dialog>
  );
}
