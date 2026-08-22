import { describe, expect, it } from "vitest";
import {
  INITIAL_JITTER_MS,
  INTERRUPT_GUARD_MS,
  JITTER_GROWTH_MS,
  MAX_QUEUED_CHUNKS,
  MIN_JITTER_MS,
  InterruptGuard,
  JitterBuffer,
  PlaybackQueue,
  type PlayedChunk,
  type QueuedChunk,
  estimateSpokenText,
} from "./playback";

function chunk(seq: number, text = `chunk-${seq}`): QueuedChunk {
  return { seq, audio: new Int16Array([1, 2, 3]), sampleRate: 24_000, textFragment: text };
}

describe("JitterBuffer", () => {
  it("starts at 120ms", () => {
    expect(new JitterBuffer().valueMs).toBe(INITIAL_JITTER_MS);
  });

  it("grows by 40ms on each underrun", () => {
    const jb = new JitterBuffer();
    jb.growOnUnderrun();
    expect(jb.valueMs).toBe(INITIAL_JITTER_MS + JITTER_GROWTH_MS);
    jb.growOnUnderrun();
    expect(jb.valueMs).toBe(INITIAL_JITTER_MS + 2 * JITTER_GROWTH_MS);
  });

  it("never shrinks below 60ms", () => {
    const jb = new JitterBuffer(70);
    jb.shrink(100);
    expect(jb.valueMs).toBe(MIN_JITTER_MS);
  });
});

describe("PlaybackQueue", () => {
  it("dequeues in seq order even when enqueued out of order", () => {
    const q = new PlaybackQueue();
    q.enqueue(chunk(2));
    q.enqueue(chunk(0));
    q.enqueue(chunk(1));
    expect(q.dequeueNext()?.seq).toBe(0);
    expect(q.dequeueNext()?.seq).toBe(1);
    expect(q.dequeueNext()?.seq).toBe(2);
  });

  it("drops a chunk arriving at or before the playhead", () => {
    const q = new PlaybackQueue();
    q.enqueue(chunk(5));
    q.dequeueNext(); // playhead now at seq 5
    q.enqueue(chunk(3)); // stale
    q.enqueue(chunk(5)); // stale (already played)
    expect(q.length).toBe(0);
  });

  it("ignores an exact duplicate seq already queued", () => {
    const q = new PlaybackQueue();
    q.enqueue(chunk(1));
    q.enqueue(chunk(1));
    expect(q.length).toBe(1);
  });

  it("drops the oldest queued chunk under backpressure, never grows unboundedly", () => {
    const q = new PlaybackQueue();
    for (let seq = 0; seq < MAX_QUEUED_CHUNKS + 5; seq++) {
      q.enqueue(chunk(seq));
    }
    expect(q.length).toBe(MAX_QUEUED_CHUNKS);
    // the oldest (lowest-seq) entries were the ones dropped
    expect(q.dequeueNext()?.seq).toBe(5);
  });

  it("clear() empties the queue immediately (used by stop-on-speech)", () => {
    const q = new PlaybackQueue();
    q.enqueue(chunk(0));
    q.enqueue(chunk(1));
    q.clear();
    expect(q.length).toBe(0);
    expect(q.dequeueNext()).toBeUndefined();
  });

  it("a single-chunk reply is never clipped — the one chunk dequeues intact", () => {
    const q = new PlaybackQueue();
    q.enqueue(chunk(0, "Sure."));
    const only = q.dequeueNext();
    expect(only?.textFragment).toBe("Sure.");
    expect(q.length).toBe(0);
  });
});

describe("InterruptGuard", () => {
  it("does not trigger on a 200ms blip (under the 250ms guard)", () => {
    const guard = new InterruptGuard();
    let triggered = false;
    for (let i = 0; i < 10; i++) {
      // 10 * 20ms = 200ms
      triggered = guard.observeVoicedFrame() || triggered;
    }
    expect(triggered).toBe(false);
  });

  it("triggers once sustained voiced audio crosses the guard interval", () => {
    const guard = new InterruptGuard();
    let triggered = false;
    for (let i = 0; i < 13; i++) {
      // 13 * 20ms = 260ms >= 250ms
      triggered = guard.observeVoicedFrame() || triggered;
    }
    expect(triggered).toBe(true);
  });

  it("a silent frame resets the streak", () => {
    const guard = new InterruptGuard();
    for (let i = 0; i < 10; i++) guard.observeVoicedFrame(); // 200ms
    guard.observeSilentFrame();
    let triggered = false;
    for (let i = 0; i < 10; i++) {
      triggered = guard.observeVoicedFrame() || triggered; // another 200ms, still under 250 since it restarted
    }
    expect(triggered).toBe(false);
  });

  it("respects the exact boundary", () => {
    expect(INTERRUPT_GUARD_MS).toBe(250);
    const guard = new InterruptGuard(250, 20);
    for (let i = 0; i < 12; i++) guard.observeVoicedFrame(); // 240ms
    const atBoundary = guard.observeVoicedFrame(); // 260ms — crosses 250
    expect(atBoundary).toBe(true);
  });
});

describe("estimateSpokenText", () => {
  it("includes only chunks that actually started playing", () => {
    const chunks: PlayedChunk[] = [
      { seq: 0, textFragment: "So last quarter", startedPlaying: true },
      { seq: 1, textFragment: "we rebuilt the pipeline", startedPlaying: true },
      { seq: 2, textFragment: "and improved throughput", startedPlaying: false },
    ];
    expect(estimateSpokenText(chunks)).toBe("So last quarter we rebuilt the pipeline");
  });

  it("returns an empty string when nothing had started playing", () => {
    const chunks: PlayedChunk[] = [{ seq: 0, textFragment: "never heard", startedPlaying: false }];
    expect(estimateSpokenText(chunks)).toBe("");
  });
});
