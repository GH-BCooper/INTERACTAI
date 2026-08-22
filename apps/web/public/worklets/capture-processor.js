// Runs on the dedicated audio-rendering thread (docs/phase-1-LEARN.md §3). No DOM, no fetch,
// no imports — this file is loaded standalone via `audioWorklet.addModule()` and must stay
// dependency-free. See docs/decisions/0004-worklet-resampling.md for the resampling approach.

const TARGET_RATE = 16000;
const FRAME_SAMPLES = 320; // 20ms @ 16kHz — the frozen upstream frame size
const METER_INTERVAL_MS = 50; // ~20 Hz level-meter updates, computed here (never on the main thread)

class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // Resampling state (streaming linear interpolation, ratio = contextRate / 16000).
    this._ratio = sampleRate / TARGET_RATE;
    this._nextOutPos = 0; // fractional position, in *input*-sample units, of the next output sample
    this._lastInputIndex = -1;
    this._prevInput = 0;
    this._currInput = 0;

    // Preallocated accumulator for resampled (16kHz) samples awaiting frame emission. Sized
    // generously so a single process() call (128 samples upstream, at most ~128 output samples
    // since ratio >= 1) can never overflow it before the while-loop below drains it.
    this._resampleBuf = new Float32Array(FRAME_SAMPLES * 4);
    this._resampleLen = 0;

    // Meter accumulation (pre-resample, on the raw input signal).
    this._meterSumSquares = 0;
    this._meterCount = 0;
    this._meterIntervalSamples = Math.max(1, Math.round((sampleRate * METER_INTERVAL_MS) / 1000));
    this._samplesSinceMeter = 0;

    this._framesEmitted = 0;
    this._muted = false;

    this.port.onmessage = (event) => {
      if (event.data && event.data.type === "mute") {
        this._muted = !!event.data.muted;
      }
    };
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || channel.length === 0) return true; // no input yet (e.g. device warming up)

    for (let i = 0; i < channel.length; i++) {
      const raw = channel[i];
      const sample = this._muted ? 0 : raw;

      this._meterSumSquares += raw * raw; // meter reflects the true mic signal, not the mute gate
      this._meterCount++;
      this._samplesSinceMeter++;
      if (this._samplesSinceMeter >= this._meterIntervalSamples) {
        const rms = Math.sqrt(this._meterSumSquares / this._meterCount);
        this.port.postMessage({ type: "meter", rms, atMs: this._framesEmitted * 20 });
        this._meterSumSquares = 0;
        this._meterCount = 0;
        this._samplesSinceMeter = 0;
      }

      this._feedResampler(sample);
    }

    while (this._resampleLen >= FRAME_SAMPLES) {
      this._emitFrame();
    }

    return true; // returning false tears the node down silently — never do that
  }

  // Streaming linear-interpolation resampler. For an exact-integer ratio (e.g. 48000/16000=3)
  // every emitted sample lands exactly on an input sample (frac === 0 always), which is
  // arithmetically identical to naive decimation — no separate code path needed.
  _feedResampler(sample) {
    this._prevInput = this._currInput;
    this._currInput = sample;
    this._lastInputIndex++;

    while (Math.floor(this._nextOutPos) + 1 <= this._lastInputIndex) {
      const idx0 = Math.floor(this._nextOutPos);
      const frac = this._nextOutPos - idx0;
      // Invariant: idx0 === this._lastInputIndex - 1 here (ratio >= 1, checked every sample).
      const interpolated = this._prevInput + frac * (this._currInput - this._prevInput);
      if (this._resampleLen < this._resampleBuf.length) {
        this._resampleBuf[this._resampleLen++] = interpolated;
      }
      this._nextOutPos += this._ratio;
    }
  }

  _emitFrame() {
    const frame = new Int16Array(FRAME_SAMPLES);
    for (let i = 0; i < FRAME_SAMPLES; i++) {
      const s = Math.max(-1, Math.min(1, this._resampleBuf[i]));
      frame[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this._resampleBuf.copyWithin(0, FRAME_SAMPLES, this._resampleLen);
    this._resampleLen -= FRAME_SAMPLES;
    this._framesEmitted++;

    this.port.postMessage(
      { type: "frame", frameIndex: this._framesEmitted - 1, buffer: frame.buffer },
      [frame.buffer],
    );
  }
}

registerProcessor("capture-processor", CaptureProcessor);
