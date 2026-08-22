import { clsx } from "clsx";
import { Mic, Loader2, Volume2, WifiOff, CircleCheck } from "lucide-react";

import type { ClientState } from "@/lib/ws-types";

const LABEL: Record<ClientState, string> = {
  your_turn: "Your turn — go ahead",
  thinking: "Thinking",
  speaking: "Speaking",
  connection_trouble: "Reconnecting…",
  ended: "Session ended",
};

const ICON: Record<ClientState, typeof Mic> = {
  your_turn: Mic,
  thinking: Loader2,
  speaking: Volume2,
  connection_trouble: WifiOff,
  ended: CircleCheck,
};

/** Task 3.2 non-negotiable: "Screen reader announces every turn state change via an ARIA live
 * region." This is that region — `role="status"` + `aria-live="polite"` means every
 * `client_state` change is read aloud without the screen reader needing focus here. Also the
 * page's one *visible* non-verbal "your turn" signal (Task 3.2: "unmistakable, non-verbal"). */
export function TurnIndicator({ clientState }: { clientState: ClientState }) {
  const Icon = ICON[clientState];
  return (
    <div
      role="status"
      aria-live="polite"
      className={clsx(
        "flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-medium",
        clientState === "your_turn" && "border-[var(--accent)] text-[var(--accent)]",
        clientState === "connection_trouble" && "border-[var(--danger)] text-[var(--danger)]",
      )}
    >
      <Icon size={16} className={clientState === "thinking" ? "animate-thinking" : undefined} />
      {LABEL[clientState]}
    </div>
  );
}
