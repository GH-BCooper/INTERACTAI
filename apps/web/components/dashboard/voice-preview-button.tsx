"use client";

import { Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { fetchVoicePreviewUrl } from "@/lib/audio/voice-preview";

/** Task 4.2: "Voice preview plays a pre-synthesised sample without starting a session." */
export function VoicePreviewButton({ personaId, size = "sm" }: { personaId: string; size?: "sm" | "md" }) {
  const [state, setState] = useState<"idle" | "loading" | "playing" | "failed">("idle");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Stop the sample if the dialog/page that owns this button goes away mid-play.
  useEffect(
    () => () => {
      audioRef.current?.pause();
    },
    [],
  );

  async function play() {
    setState("loading");
    const url = await fetchVoicePreviewUrl(personaId);
    if (!url) {
      setState("failed");
      return;
    }
    const audio = new Audio(url);
    audioRef.current = audio;
    audio.addEventListener("ended", () => {
      setState("idle");
      URL.revokeObjectURL(url);
    });
    setState("playing");
    void audio.play().catch(() => setState("failed"));
  }

  return (
    <Button variant="secondary" size={size} onClick={() => void play()} disabled={state === "loading" || state === "playing"}>
      <Volume2 size={14} aria-hidden />
      {state === "loading" ? "Loading…" : state === "playing" ? "Playing…" : state === "failed" ? "Preview unavailable" : "Preview voice"}
    </Button>
  );
}
