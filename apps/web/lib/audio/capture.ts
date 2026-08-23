/**
 * Main-thread capture wrapper (Task 1.2a). The AudioWorklet
 * (public/worklets/capture-processor.js) does the resampling, 20ms framing and RMS metering on
 * the dedicated audio thread; this module owns the WebSocket-facing concerns that belong on the
 * main thread: assigning the monotonic upstream `seq`, building the frozen wire frame, and
 * wiring `getUserMedia`/`AudioContext` together.
 *
 * The framing/sequencing logic below is a pure function precisely so it's testable without a
 * real AudioContext (jsdom/vitest has no Web Audio implementation). The AudioContext glue
 * (`createMicCapture`) is deliberately thin — see the Phase 1 report for what that part still
 * needs manual, in-browser verification.
 */

import { encodeUpstreamFrame, UPSTREAM_FRAME_SAMPLES } from "./protocol";

export interface WorkletFrameMessage {
  type: "frame";
  frameIndex: number;
  buffer: ArrayBuffer;
}

export interface WorkletMeterMessage {
  type: "meter";
  rms: number;
  atMs: number;
}

export type WorkletMessage = WorkletFrameMessage | WorkletMeterMessage;

/** Assigns the next monotonic upstream seq and builds the 652-byte wire frame for one worklet
 * frame message. `frameIndex * 20` (from the worklet, sample-count-derived) is used as the
 * timestamp rather than wall-clock arrival time, since message-port delivery is subject to
 * main-thread scheduling jitter the sample count is not. */
export function buildUpstreamWireFrame(seq: number, message: WorkletFrameMessage): ArrayBuffer {
  const payload = new Int16Array(message.buffer);
  if (payload.length !== UPSTREAM_FRAME_SAMPLES) {
    throw new Error(`expected ${UPSTREAM_FRAME_SAMPLES}-sample frame, got ${payload.length}`);
  }
  return encodeUpstreamFrame(seq, message.frameIndex * 20, payload);
}

export interface MicCaptureHandlers {
  onFrame: (wireFrame: ArrayBuffer) => void;
  onMeter: (rms: number, atMs: number) => void;
  /** Task 3.2 edge case: "Mic permission revoked mid-session -> detect via track `ended`
   * event." The browser fires this on the MediaStreamTrack itself when the OS/browser yanks
   * access out from under an already-running capture (Chrome's mic toggle, a revoked OS
   * permission) — distinct from the user never granting it in the first place, and from a
   * `devicechange` (a different device disappearing, not this one being revoked). Optional so
   * existing callers that don't care about this signal are unaffected. */
  onTrackEnded?: () => void;
}

export interface MicCaptureHandle {
  setMuted: (muted: boolean) => void;
  stop: () => Promise<void>;
}

export interface MicCaptureConstraints {
  deviceId?: string;
  echoCancellation?: boolean;
  noiseSuppression?: boolean;
}

/** Wires getUserMedia -> AudioContext -> AudioWorkletNode -> handlers. Requires a real browser
 * environment (AudioWorklet, MediaDevices); not exercised by the vitest (node) suite — see
 * `buildUpstreamWireFrame` above for the part of this file that is.
 *
 * `constraints` is optional and defaults to exactly the previous hardcoded behaviour — Task 4.4's
 * Settings > Audio page (device picker, echo-cancellation/noise-suppression toggles) is the only
 * caller that ever passes it explicitly; the live practice room's own default capture is
 * unaffected unless the caller opts in. */
export async function createMicCapture(
  handlers: MicCaptureHandlers,
  constraints?: MicCaptureConstraints,
): Promise<MicCaptureHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: constraints?.echoCancellation ?? true,
      noiseSuppression: constraints?.noiseSuppression ?? true,
      autoGainControl: true,
      channelCount: 1,
      ...(constraints?.deviceId ? { deviceId: { exact: constraints.deviceId } } : {}),
    },
  });

  const ctx = new AudioContext();
  await ctx.audioWorklet.addModule("/worklets/capture-processor.js");

  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "capture-processor");

  let seq = 0;
  node.port.onmessage = (event: MessageEvent<WorkletMessage>) => {
    const msg = event.data;
    if (msg.type === "frame") {
      handlers.onFrame(buildUpstreamWireFrame(seq, msg));
      seq = (seq + 1) >>> 0;
    } else if (msg.type === "meter") {
      handlers.onMeter(msg.rms, msg.atMs);
    }
  };

  source.connect(node);

  const track = stream.getAudioTracks()[0];
  if (track) track.onended = () => handlers.onTrackEnded?.();

  return {
    setMuted(muted: boolean) {
      node.port.postMessage({ type: "mute", muted });
    },
    async stop() {
      node.disconnect();
      source.disconnect();
      for (const track of stream.getTracks()) track.stop();
      await ctx.close();
    },
  };
}
