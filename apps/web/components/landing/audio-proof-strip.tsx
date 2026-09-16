"use client";

import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface ProofTurn {
  id: string;
  answer: string;
  reply: string;
  startMs: number;
  endMs: number;
  e2eMs: number | null;
}

/** Phase 6 TASK 6.6 — "a real recorded exchange, playable inline, with the latency figure shown
 * against each turn." One <audio> element over the demo recording; each row plays its own slice. */
export function AudioProofStrip({ src, turns }: { src: string; turns: ProofTurn[] }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const stopAt = useRef<number>(0);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onTime = () => {
      if (el.currentTime * 1000 >= stopAt.current) {
        el.pause();
        setPlaying(null);
      }
    };
    el.addEventListener("timeupdate", onTime);
    return () => el.removeEventListener("timeupdate", onTime);
  }, []);

  function toggle(turn: ProofTurn) {
    const el = audioRef.current;
    if (!el) return;
    if (playing === turn.id) {
      el.pause();
      setPlaying(null);
      return;
    }
    el.currentTime = turn.startMs / 1000;
    stopAt.current = turn.endMs;
    void el.play();
    setPlaying(turn.id);
  }

  return (
    <div className="flex flex-col gap-2">
      <audio ref={audioRef} src={src} preload="none" />
      {turns.map((t, i) => (
        <button
          key={t.id}
          type="button"
          onClick={() => toggle(t)}
          className="group grid grid-cols-[2rem_1fr_auto] items-center gap-3 rounded-lg border bg-[var(--bg-card)] p-3 text-left transition-colors hover:bg-[var(--bg-raised)]"
          aria-label={`${playing === t.id ? "Pause" : "Play"} exchange ${i + 1}`}
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--accent)] text-[var(--text-on-accent)]">
            {playing === t.id ? <Pause size={14} /> : <Play size={14} />}
          </span>
          <span className="min-w-0 text-sm">
            <span className="block truncate text-[var(--text-secondary)]">Candidate: “{t.answer}”</span>
            <span className="block truncate">Interviewer: “{t.reply}”</span>
          </span>
          <span className="text-right">
            <span className="block font-mono text-sm">{t.e2eMs === null ? "—" : `${t.e2eMs.toLocaleString()} ms`}</span>
            <span className="block text-xs text-[var(--text-tertiary)]">end of speech → first word</span>
          </span>
        </button>
      ))}
    </div>
  );
}
