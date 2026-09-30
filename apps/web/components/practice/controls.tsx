import { clsx } from "clsx";
import { Captions, CaptionsOff, Mic, MicOff, PhoneOff } from "lucide-react";

import { MicLevelMeter } from "./mic-level-meter";

interface ControlsProps {
  muted: boolean;
  onToggleMute: () => void;
  captionsEnabled: boolean;
  onToggleCaptions: () => void;
  onEndClick: () => void;
  meterRef: React.RefObject<HTMLDivElement | null>;
}

const ROUND =
  "flex h-11 w-11 items-center justify-center rounded-full border text-[var(--text-primary)] transition-colors duration-150 hover:bg-[var(--bg-raised)]";

/** Task 3.2: "Controls. Mute, end session, captions toggle. Nothing else." The keyboard
 * shortcuts (M, C, Esc — wired in practice-room.tsx) are named in each tooltip. */
export function Controls({
  muted,
  onToggleMute,
  captionsEnabled,
  onToggleCaptions,
  onEndClick,
  meterRef,
}: ControlsProps) {
  return (
    <div className="flex items-center gap-4">
      <MicLevelMeter ref={meterRef} />

      <button
        type="button"
        onClick={onToggleMute}
        aria-pressed={muted}
        aria-label={muted ? "Unmute microphone" : "Mute microphone"}
        aria-keyshortcuts="M"
        title={`${muted ? "Unmute" : "Mute"} (M)`}
        className={clsx(ROUND, muted && "border-[var(--status-bad)] text-[var(--status-bad)]")}
      >
        {muted ? <MicOff size={18} /> : <Mic size={18} />}
      </button>

      <button
        type="button"
        onClick={onToggleCaptions}
        aria-pressed={captionsEnabled}
        aria-label={captionsEnabled ? "Turn captions off" : "Turn captions on"}
        aria-keyshortcuts="C"
        title={`Captions ${captionsEnabled ? "off" : "on"} (C)`}
        className={ROUND}
      >
        {captionsEnabled ? <Captions size={18} /> : <CaptionsOff size={18} />}
      </button>

      <button
        type="button"
        onClick={onEndClick}
        aria-label="End session"
        aria-keyshortcuts="Escape"
        title="End session (Esc, then confirm)"
        className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--danger)] text-[var(--text-on-accent)] transition-colors duration-150 hover:bg-[var(--danger-hover)]"
      >
        <PhoneOff size={18} />
      </button>
    </div>
  );
}
