/**
 * Browser playback (Task 1.5c) and stop-on-speech (Task 1.5d).
 *
 * The scheduling/ordering/backpressure/interrupt-guard logic below is deliberately pure and
 * framework-free — `JitterBuffer`, `PlaybackQueue`, `InterruptGuard` and `estimateSpokenText`
 * touch no Web Audio API and are exercised directly by `playback.test.ts`. `PersonaPlayback`
 * is the thin glue that wires them to a real `AudioContext`; jsdom/vitest has no Web Audio
 * implementation, so that class is not unit-tested here — see the Phase 1 report for what
 * still needs manual, in-browser verification.
 */

import { DOWNSTREAM_SAMPLE_RATE } from "./protocol";

export const INITIAL_JITTER_MS = 120;
export const JITTER_GROWTH_MS = 40;
export const MIN_JITTER_MS = 60;
export const MAX_QUEUED_CHUNKS = 8;
export const INTERRUPT_GUARD_MS = 250;
export const FRAME_MS = 20;

/** Adaptive jitter buffer (Task 1.5c): starts at 120ms, grows by 40ms on each observed
 * underrun, never shrinks below 60ms. No automatic shrink trigger is specified anywhere in
 * the spec, so `shrink()` exists (and is floored) but nothing calls it yet — that's a
 * deliberate scope limit, not an oversight. */
export class JitterBuffer {
  private ms: number;

  constructor(initialMs: number = INITIAL_JITTER_MS) {
    this.ms = initialMs;
  }

  get valueMs(): number {
    return this.ms;
  }

  growOnUnderrun(): void {
    this.ms += JITTER_GROWTH_MS;
  }

  shrink(byMs: number): void {
    this.ms = Math.max(MIN_JITTER_MS, this.ms - byMs);
  }
}

export interface QueuedChunk {
  seq: number;
  audio: Int16Array;
  sampleRate: number;
  textFragment: string;
}

/** Reorders by `seq`, drops anything at or before the playhead, and caps queue depth by
 * dropping the *oldest* queued chunk under backpressure (Task 1.5c edge cases) — never
 * buffers unboundedly. */
export class PlaybackQueue {
  private queue: QueuedChunk[] = [];
  private lastDequeuedSeq = -1;

  enqueue(chunk: QueuedChunk): void {
    if (chunk.seq <= this.lastDequeuedSeq) return; // stale: at or before the playhead
    if (this.queue.some((c) => c.seq === chunk.seq)) return; // duplicate delivery

    const insertAt = this.queue.findIndex((c) => c.seq > chunk.seq);
    if (insertAt === -1) this.queue.push(chunk);
    else this.queue.splice(insertAt, 0, chunk);

    while (this.queue.length > MAX_QUEUED_CHUNKS) {
      this.queue.shift(); // drop the oldest (lowest-seq, longest-waiting) queued chunk
    }
  }

  dequeueNext(): QueuedChunk | undefined {
    const next = this.queue.shift();
    if (next) this.lastDequeuedSeq = next.seq;
    return next;
  }

  clear(): void {
    this.queue = [];
  }

  get length(): number {
    return this.queue.length;
  }
}

/** Tracks consecutive voiced-frame duration during `speaking` and reports when the guard
 * interval (250ms) is crossed (Task 1.5d) — a brief 200ms blip must not count. */
export class InterruptGuard {
  private voicedMs = 0;

  constructor(
    private readonly guardMs: number = INTERRUPT_GUARD_MS,
    private readonly frameMs: number = FRAME_MS,
  ) {}

  /** Returns true the instant sustained voiced audio crosses the guard interval. */
  observeVoicedFrame(): boolean {
    this.voicedMs += this.frameMs;
    return this.voicedMs >= this.guardMs;
  }

  observeSilentFrame(): void {
    this.voicedMs = 0;
  }

  reset(): void {
    this.voicedMs = 0;
  }
}

export interface PlayedChunk {
  seq: number;
  textFragment: string;
  startedPlaying: boolean;
}

/** Task 1.5d: "the text actually spoken (estimate from chunks that started playing, not from
 * chunks generated)". A chunk queued but never started is never heard, and counting it would
 * corrupt both the transcript and the scoring context. */
export function estimateSpokenText(chunks: PlayedChunk[]): string {
  return chunks
    .filter((c) => c.startedPlaying)
    .map((c) => c.textFragment)
    .join(" ")
    .trim();
}

export interface TruncationResult {
  truncatedText: string;
}

/**
 * Thin AudioContext glue (not unit-tested — see module docstring). `AudioContext` at
 * `DOWNSTREAM_SAMPLE_RATE`; scheduled against `ctx.currentTime`, never `setTimeout`, per
 * Task 1.5c. Deliberately never uses an `<audio>` element — it cannot gaplessly concatenate.
 */
export class PersonaPlayback {
  private readonly ctx: AudioContext;
  private readonly jitter = new JitterBuffer();
  private readonly queue = new PlaybackQueue();
  private activeSources: AudioBufferSourceNode[] = [];
  private nextStartTime = 0;
  private playedChunks: PlayedChunk[] = [];

  constructor(ctx?: AudioContext) {
    this.ctx = ctx ?? new AudioContext({ sampleRate: DOWNSTREAM_SAMPLE_RATE });
  }

  enqueueChunk(seq: number, payload: Int16Array, textFragment: string): void {
    this.queue.enqueue({ seq, audio: payload, sampleRate: DOWNSTREAM_SAMPLE_RATE, textFragment });
    this.scheduleNext();
  }

  private scheduleNext(): void {
    const chunk = this.queue.dequeueNext();
    if (!chunk) return;

    const buffer = this.ctx.createBuffer(1, chunk.audio.length, chunk.sampleRate);
    const floatData = buffer.getChannelData(0);
    for (let i = 0; i < chunk.audio.length; i++) {
      const s = chunk.audio[i]!;
      floatData[i] = s < 0 ? s / 0x8000 : s / 0x7fff;
    }

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);

    const startAt = Math.max(this.ctx.currentTime + this.jitter.valueMs / 1000, this.nextStartTime);
    source.start(startAt);
    this.nextStartTime = startAt + buffer.duration;
    this.activeSources.push(source);

    const played: PlayedChunk = { seq: chunk.seq, textFragment: chunk.textFragment, startedPlaying: false };
    this.playedChunks.push(played);
    const delayMs = Math.max(0, (startAt - this.ctx.currentTime) * 1000);
    setTimeout(() => {
      played.startedPlaying = true;
    }, delayMs);

    source.onended = () => {
      this.activeSources = this.activeSources.filter((s) => s !== source);
    };
  }

  /** Task 1.5d: stop everything scheduled, clear the queue, and report what was actually
   * heard so far. */
  interrupt(): TruncationResult {
    for (const source of this.activeSources) {
      try {
        source.stop();
      } catch {
        // already stopped/ended — fine
      }
    }
    this.activeSources = [];
    this.queue.clear();
    const truncatedText = estimateSpokenText(this.playedChunks);
    this.playedChunks = [];
    this.nextStartTime = 0;
    return { truncatedText };
  }
}
