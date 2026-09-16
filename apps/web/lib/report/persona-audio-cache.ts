import { sessions } from "@/lib/api/resources";

export const REALTIME_HTTP_URL = process.env.NEXT_PUBLIC_REALTIME_HTTP_URL ?? "http://localhost:8080";

const TOKEN_EXPIRY_SAFETY_MARGIN_MS = 5000;

/**
 * Task 3.4d: "Persona audio is regenerated on demand during replay from the transcript +
 * voice_id — it was never stored (CLAUDE.md §1.8). Cache regenerated audio client-side for the
 * session so scrubbing back does not re-synthesise." One instance per report view; disposed
 * (object URLs revoked) when the report unmounts.
 */
export class PersonaAudioCache {
  private readonly objectUrls = new Map<string, string>();
  private replayToken: string | null = null;
  private replayTokenExpiresAt = 0;

  constructor(
    private readonly sessionId: string,
    private readonly realtimeHttpUrl: string = REALTIME_HTTP_URL,
    // Phase 6 TASK 6.1c: the observability waterfall mints its token through the admin route.
    private readonly mintToken: (sessionId: string) => Promise<{ token: string; expires_in: number }> =
      sessions.mintReplayToken,
  ) {}

  private async ensureReplayToken(): Promise<string> {
    if (this.replayToken && Date.now() < this.replayTokenExpiresAt) return this.replayToken;
    const { token, expires_in } = await this.mintToken(this.sessionId);
    this.replayToken = token;
    this.replayTokenExpiresAt = Date.now() + expires_in * 1000 - TOKEN_EXPIRY_SAFETY_MARGIN_MS;
    return token;
  }

  /** Returns a playable object URL, or `null` on any failure — Task 3.4's edge case: "Persona
   * audio regeneration fails -> transcript still readable, seek still works on user turns." A
   * failure here is never allowed to throw into the caller's render path. */
  async getAudioUrl(turnId: string, text: string, voiceId: string): Promise<string | null> {
    const cached = this.objectUrls.get(turnId);
    if (cached) return cached;

    try {
      const token = await this.ensureReplayToken();
      const resp = await fetch(`${this.realtimeHttpUrl}/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, session_id: this.sessionId, text, voice_id: voiceId }),
      });
      if (!resp.ok) return null;
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      this.objectUrls.set(turnId, url);
      return url;
    } catch {
      return null;
    }
  }

  dispose(): void {
    for (const url of this.objectUrls.values()) URL.revokeObjectURL(url);
    this.objectUrls.clear();
  }
}
