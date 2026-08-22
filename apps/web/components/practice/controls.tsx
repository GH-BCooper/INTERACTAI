import { Captions, Mic, MicOff, PhoneOff } from "lucide-react";

import { MicLevelMeter } from "./mic-level-meter";

interface ControlsProps {
  muted: boolean;
  onToggleMute: () => void;
  captionsEnabled: boolean;
  onToggleCaptions: () => void;
  onEndClick: () => void;
  meterRef: React.RefObject<HTMLDivElement | null>;
}

/** Task 3.2: "Controls. Mute, end session, captions toggle. Nothing else." */
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
        className="flex h-10 w-10 items-center justify-center rounded-full border text-[var(--text-primary)] hover:bg-[var(--bg-raised)]"
      >
        {muted ? <MicOff size={18} /> : <Mic size={18} />}
      </button>

      <button
        type="button"
        onClick={onToggleCaptions}
        aria-pressed={captionsEnabled}
        aria-label={captionsEnabled ? "Turn captions off" : "Turn captions on"}
        className="flex h-10 w-10 items-center justify-center rounded-full border text-[var(--text-primary)] hover:bg-[var(--bg-raised)]"
      >
        <Captions size={18} />
      </button>

      <button
        type="button"
        onClick={onEndClick}
        aria-label="End session"
        className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--danger)] text-[var(--text-on-accent)] hover:bg-[var(--danger-hover)]"
      >
        <PhoneOff size={18} />
      </button>
    </div>
  );
}
