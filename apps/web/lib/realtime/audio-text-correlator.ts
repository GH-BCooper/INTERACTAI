/**
 * The wire protocol sends three separate messages per synthesized chunk — `audio_chunk_meta`
 * (JSON), the binary TTS frame, then `persona_text` (JSON) with that chunk's own text — in that
 * strict order (services/realtime/app/sink.py::send_audio_chunk is fully awaited before the
 * caller's `send_persona_text`; see turn.py's `_emit_chunk` loop). None of the three share a
 * single id: `audio_chunk_meta.seq` and `persona_text.seq` are this connection's ordinary
 * per-message counter, while the binary frame's own `seq` field is a *separate* downstream-audio-
 * only counter (`WsTurnSink._downstream_seq`). The only thing tying a chunk's audio to its text
 * is arrival order, which this class turns into a correlation without assuming anything stronger
 * than "metas, frames and texts each arrive in the order they were sent."
 */

export interface CorrelatedChunk {
  turnId: string;
  seq: number;
  text: string;
}

interface PendingEntry {
  turnId: string;
  seq: number | null;
  text: string | null;
}

export class AudioTextCorrelator {
  private pending: PendingEntry[] = [];

  observeMeta(turnId: string): void {
    this.pending.push({ turnId, seq: null, text: null });
  }

  /** Call with every downstream binary frame's decoded `seq`. */
  observeFrame(seq: number): CorrelatedChunk | null {
    const entry = this.pending.find((e) => e.seq === null);
    if (!entry) return null; // a frame with no matching meta — drop rather than crash
    entry.seq = seq;
    return this.complete(entry);
  }

  /** Call with a non-empty `persona_text` delta only — the final `done: true` terminator
   * (always an empty string) is not chunk text and must be filtered before calling this. */
  observeText(text: string): CorrelatedChunk | null {
    const entry = this.pending.find((e) => e.text === null);
    if (!entry) return null;
    entry.text = text;
    return this.complete(entry);
  }

  private complete(entry: PendingEntry): CorrelatedChunk | null {
    if (entry.seq === null || entry.text === null) return null;
    this.pending = this.pending.filter((e) => e !== entry);
    return { turnId: entry.turnId, seq: entry.seq, text: entry.text };
  }

  /** A new turn (or a reconnect) starting mid-stream should never carry over a stale half-match. */
  reset(): void {
    this.pending = [];
  }
}
