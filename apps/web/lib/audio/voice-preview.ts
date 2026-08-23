import { personas } from "@/lib/api/resources";
import { REALTIME_HTTP_URL } from "@/lib/report/persona-audio-cache";

/**
 * Task 4.2: "Voice preview plays a pre-synthesised sample without starting a session." Mirrors
 * lib/report/persona-audio-cache.ts's token-then-fetch shape exactly, against realtime's sibling
 * `POST /synthesize-preview` endpoint — a fixed sentence, no session involved.
 */
export async function fetchVoicePreviewUrl(personaId: string): Promise<string | null> {
  try {
    const { token, voice_id } = await personas.mintVoicePreviewToken(personaId);
    const resp = await fetch(`${REALTIME_HTTP_URL}/synthesize-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, voice_id }),
    });
    if (!resp.ok) return null;
    const blob = await resp.blob();
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}
