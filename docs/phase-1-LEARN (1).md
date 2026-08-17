# Phase 1 — LEARN — The voice loop (days 4–8)

**Exit criterion (the Day 8 gate):** a spoken conversation works end to end from a
command-line harness, with per-stage latency recorded. **No user interface exists.**

**Study time this phase:** ~19 hours — Web Audio/AudioWorklet 6h, Silero VAD 2h,
faster-whisper 8h, Piper 3h.
**Heavy technologies:** two of the three (AudioWorklet on day 4, faster-whisper on day 6).
They are on separate days on purpose. Do not merge them.

This is the hardest week of the project and the one that decides whether it works.

---

## 0. The mental model

Everything in this phase is one idea applied five times: **nothing waits for a complete
artefact.**

```
speech ──► frames ──► VAD ──► ASR (decoding DURING speech) ──► endpoint ──► finalise
                                                                              │
                                            ┌─────────────────────────────────┘
                                            ▼
                            persona model (streaming tokens)
                                            │
                            ┌───────────────┘
                            ▼
              sentence chunker ──► TTS per chunk ──► first buffer plays
                                                     while chunk 2 synthesises
```

If you internalise nothing else this week: **streaming everywhere is worth more than every
other optimisation combined.** Prefix caching, chunk tuning and backchannel masking are
worth a few hundred milliseconds between them. Streaming is worth several seconds.

---

## 1. The latency budget, and the one thing to understand about it

| Stage | What happens | p50 | p95 |
|---|---|---|---|
| Endpoint detection | Silence window elapses. Dominated by a **chosen threshold**, not by compute. | 350 | 450 |
| ASR finalisation | Decoder flushes; punctuation and timestamps applied. Most work already happened during speech. | 100 | 180 |
| Prompt assembly | History compaction, plan state, cache-marked prefix. Pure CPU. | 15 | 30 |
| Model time to first token | The largest **controllable** term. | 250 | 400 |
| First chunk assembly | Tokens accumulate to the first clause boundary. | 70 | 120 |
| Synthesis of first chunk | TTS produces the first audio buffer. | 150 | 250 |
| Transport + jitter buffer | Network hop plus the deliberate playback buffer. | 100 | 160 |
| **Sum of stage targets** | | **1035** | **1590** |
| **Measured end-to-end goal** | End of speech → first audible word | **≤1100** | **≤1400** |

### Percentiles do not add

The end-to-end p95 target (1400 ms) is **lower** than the sum of the per-stage p95 targets
(1590 ms). That is not an error and it is not sloppiness.

A run is only at the 95th percentile end to end if **several stages are slow
simultaneously**, which is much rarer than any single stage being slow. Sizing a budget by
summing per-stage p95s over-provisions badly.

So: **measure the end-to-end distribution directly**, and use per-stage percentiles only to
find which component to attack.

Being able to explain this unprompted is exactly the question a senior engineer asks to see
whether you understood your numbers or copied them from somewhere. Learn it properly.

### Where the budget actually goes

Note that **endpoint detection is the single largest term** at 350–450 ms, and it is not
compute — it is a threshold you chose. That means the cheapest latency win available to you
is not a faster model; it is better endpointing. Which is also the thing most likely to
infuriate users if you get it wrong. That tension is §4.

---

## 2. Audio fundamentals you must not get wrong

### The numbers

```
Sample rate    16000 Hz      (what ASR wants; Whisper resamples anything else internally)
Channels       1 (mono)
Format         16-bit signed little-endian PCM  ("pcm_s16le", Int16Array in JS)
Frame          20 ms = 320 samples = 640 bytes
Bitrate        16000 × 2 = 32000 bytes/sec ≈ 1.9 MB per minute
```

**Memorise 320 samples / 640 bytes per frame.** You will use it constantly, and when a buffer
length is not a multiple of 640 you have a framing bug, immediately visible.

### Sample rate mismatch: the chipmunk bug

Your microphone gives you whatever the `AudioContext` runs at — usually 48000 Hz, sometimes
44100. Whisper wants 16000. Piper outputs 22050. These are three different numbers and mixing
any two produces audio that plays at the wrong pitch and speed.

There is no error message. It just sounds wrong. Symptoms:

- Playback sounds **fast and high** → you played 16 kHz data at 22.05 kHz (ratio 1.38).
- Playback sounds **slow and deep** → the reverse.
- ASR returns confident **gibberish** → you fed it 48 kHz data labelled as 16 kHz.

The fix is to be explicit about the resample points, and there are exactly two:

```
mic @ 48000 ──[resample in the worklet]──► 16000 ──► network ──► VAD/ASR
Piper @ 22050 ──[resample server-side]──► 24000 ──► network ──► browser plays at 24000
```

Downstream, pick **one** playback rate and resample everything to it before it leaves the
server. Do not let the browser deal with per-chunk rate changes; `AudioBufferSourceNode`
will happily play a buffer at the wrong rate if you construct it carelessly.

### Float32 vs Int16

The Web Audio API works in `Float32` in the range −1.0 to 1.0. The wire format is `Int16`.
Conversion:

```js
// Float32 → Int16, with clamping. The clamp is not optional: values slightly
// outside [-1,1] happen, and without clamping they wrap around and produce a
// loud click, which sounds exactly like a hardware fault.
const i16 = new Int16Array(f32.length);
for (let i = 0; i < f32.length; i++) {
  const s = Math.max(-1, Math.min(1, f32[i]));
  i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
}
```

---

## 3. AudioWorklet — the hardest front-end topic in the project

### Why not `ScriptProcessorNode`

`ScriptProcessorNode` runs on the **main thread**. Every React re-render, every layout, every
garbage collection pause competes with your audio callback. The result is dropped frames that
appear as clicks and gaps. It is also deprecated.

`AudioWorklet` runs on a **dedicated real-time audio thread**. React cannot glitch it. This is
not a nice-to-have — it is the difference between audio that works and audio that
intermittently doesn't in a way you cannot reproduce.

### The constraints of that thread

The worklet thread is a genuinely different world:

- **No DOM, no `fetch`, no `window`, no `WebSocket`.** You cannot send from the worklet.
- Communication is `port.postMessage` only, which is asynchronous and crosses threads.
- Your `process()` callback is called every **128 samples** — about 2.7 ms at 48 kHz — and it
  must return fast. Allocating inside it causes GC pauses on the audio thread.
- It is loaded from a **separate file over the network**:
  `await ctx.audioWorklet.addModule('/worklets/capture-processor.js')`. That file cannot be
  bundled by webpack in the usual way — put it in `public/`.

### The 128 → 320 problem

`process()` gives you 128 samples. You need 320-sample (20 ms) frames at 16 kHz. 128 does not
divide into 320, and you are also resampling 48000 → 16000 on the way. So the worklet must
maintain a **ring buffer**: accumulate resampled samples, and emit a frame only when at least
320 are available.

```js
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(4096);   // preallocated — never allocate in process()
    this.n = 0;
    this.ratio = sampleRate / 16000;     // `sampleRate` is a worklet global
    this.pos = 0;
  }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;                // ← MUST return true, or the node is torn down
    // decimate/interpolate into this.buf, advance this.n
    while (this.n >= 320) {
      const frame = this.buf.slice(0, 320);
      this.port.postMessage(frame.buffer, [frame.buffer]);  // transferable — zero copy
      this.buf.copyWithin(0, 320, this.n);
      this.n -= 320;
    }
    return true;
  }
}
registerProcessor('capture-processor', CaptureProcessor);
```

Two details that matter enormously:

1. **`return true`.** Returning `false` tells the browser this node is finished and it gets
   garbage collected. Your audio stops with no error. This is a classic hour-long bug.
2. **Transfer the buffer.** `postMessage(buf, [buf])` transfers ownership instead of copying.
   At 50 messages/second the copy is survivable, but transferring is free and correct.

### Resampling honestly

48000 → 16000 is exactly 3:1, so naive decimation (take every third sample) works *and*
aliases. For speech at this quality level the aliasing is inaudible and Whisper does not care.
44100 → 16000 is not an integer ratio and needs linear interpolation at minimum.

Do the simple thing, note it in `docs/decisions/`, and move on. Do not build a polyphase
resampler. If you later want to be rigorous, the honest upgrade is to request
`sampleRate: 16000` in the `AudioContext` constructor and let the browser resample — but
support for that is inconsistent, which is why the worklet does it.

### Getting a clean stream

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: true,     // required — otherwise persona audio feeds back into VAD
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
  }
});
```

`echoCancellation` is not optional. Without it, the persona's own voice from your speakers
enters the microphone, trips the VAD, and the system interrupts itself. **Wear headphones
anyway** — echo cancellation is imperfect and you do not want to be debugging it during
endpointing tuning.

---

## 4. Endpointing — the highest-leverage twenty lines in the system

### Two objectives in direct opposition

Endpointing decides **both** the largest single term in the latency budget **and** the most
infuriating possible failure — being cut off mid-thought.

Every millisecond you remove from the silence threshold makes the system faster *and* more
likely to interrupt someone who was just thinking. There is no setting that optimises both.

Everything else in this project is engineering. **This is tuning**, and tuning requires a
labelled set of real utterance boundaries. That is why day 5 says *record and hand-mark 200
boundaries*, and why doing it on day 19 instead would be useless: you need it to tune against
on day 11.

**When in doubt, bias late.** A slightly slow system is tolerable. An interrupting one is not.

### The cascade, cheapest first

**1. Acoustic silence.** Speech probability below threshold for a continuous window.
Base 500 ms.

**2. Adaptive threshold.** The window adjusts per speaker from *their own* within-utterance
pause distribution, clamped to 350–900 ms. Costs nothing computationally; it is the single
best quality improvement available. A slow, deliberate speaker stops being cut off; a fast
speaker gets a faster system. Implementation: track the pauses that occurred *inside*
completed utterances for this session, take roughly the 90th percentile, clamp.

**3. Filler suppression.** A transcript tail ending in a hesitation marker ("um", "uh", "so",
"like", "and") extends the window. Hesitations are extremely reliable predictors of continued
speech — this is one of the highest hit-rate rules in the cascade.

**4. Syntactic incompleteness.** A trailing conjunction, preposition or article suppresses
endpointing. This is a **regular expression, not a model**, and it catches a surprising
fraction of cases. "I worked on the—" ending in "the" is almost never a finished sentence.

**5. Semantic completeness check.** Only when the window elapsed *but* the transcript looks
unfinished. One binary question to a tiny local model with an **80 ms budget**. On timeout,
end the turn — a slightly early cut beats an unbounded wait.

### Two guards around the cascade

- **Minimum utterance length** (~400 ms): below this, a detection is treated as noise. A cough
  should not become a turn.
- **Maximum turn length** (~120 s): after this the persona interrupts. That is realistic
  interviewer behaviour, not a failure — and it should be logged as `persona_interrupt`, not
  as an error.

### Measuring it

Two metrics, and you need both:

- **Endpoint precision** — of the turns the system ended, the fraction where the speaker had
  genuinely finished. Low precision means cutting people off: the worst subjective failure.
- **Endpoint recall / latency** — whether ends were detected at all, and how long after the
  true boundary.

Measured against your ≥200 hand-marked boundaries. Report both. Chasing latency without
watching precision is how you build something people hate.

---

## 5. Streaming ASR with faster-whisper

### What `faster-whisper` actually is

Whisper reimplemented on **CTranslate2**, which gives 4–8× the speed of the reference
implementation at equal accuracy, with int8 quantisation that makes CPU inference viable.
`base.en` at int8 is ~150 MB resident and runs comfortably below real time on two cores.

### Real-time factor

**RTF = seconds of compute per second of audio.** Above 1.0 the system cannot keep up and the
whole design fails — you will fall progressively further behind and latency will grow without
bound.

Measure it on your actual hardware on day 6, not in production. If RTF > 0.7 on your machine,
downgrade to `tiny.en` and report the word error rate cost rather than hiding it. An honest
"I used tiny.en on a 2-core host and here is the WER delta" is a better answer than a system
that stutters.

### Whisper is not natively streaming — the pattern you use

Whisper is a sequence-to-sequence model over 30-second windows. It has no incremental decode
API. The practical streaming pattern is:

1. Buffer audio from speech onset.
2. Every ~500 ms, re-transcribe the **whole buffered utterance so far** and emit the result as
   a *partial* hypothesis for live captions.
3. On endpointing, transcribe once more with `word_timestamps=True` and treat that as final.

This is wasteful — you transcribe the same audio repeatedly — but utterances are short
(usually under 20 s), the model is fast, and the alternative is a much more complex chunked
approach with boundary-condition bugs.

**The key insight for the latency budget:** partial hypotheses are for the *captions*, which
are cosmetic. The reason ASR finalisation is only 100 ms in the budget is that the final
transcription runs on audio that is already in memory and warm. The heavy lifting genuinely
happened during speech.

### Useful parameters

```python
segments, info = model.transcribe(
    audio,
    language="en",
    beam_size=1,                  # greedy for partials; beam 5 for the final pass
    vad_filter=False,             # you have Silero; don't run two VADs
    word_timestamps=True,         # required for evidence spans and click-to-seek
    initial_prompt=vocab_hint,    # domain vocabulary biasing — see below
    condition_on_previous_text=False,  # prevents hallucination loops on silence
)
```

**`initial_prompt` is domain vocabulary biasing** and it is genuinely effective. Feeding it
terms from the scenario and the user's resume — "Kubernetes, idempotency, PostgreSQL, Kafka,
Spotmies" — measurably improves recognition of technical nouns and proper names, which are
exactly the words that matter most in a technical interview and exactly the ones Whisper
mangles.

**`condition_on_previous_text=False` matters.** With it on, Whisper occasionally enters
repetition loops on silence or noise and emits the same phrase forty times. You will see it
eventually; turn it off now.

### Word timestamps are load-bearing

They are not a nicety. They are what makes:
- click-to-seek in the report work,
- evidence spans map to playable audio,
- and delivery metrics (pause length, speech ratio) computable.

Never disable them on the final pass.

---

## 6. Synthesis: chunking and streaming

### Sentence chunking is where perceived latency is won

The naive approach waits for the persona model to finish, then synthesises, then plays. That
adds the full generation time to your budget — often 1.5 s on its own.

Instead: accumulate streamed tokens until you hit a clause or sentence boundary, then
synthesise **that chunk** immediately and start playing it while the model is still generating
the second sentence.

**Short first chunks.** Deliberately emit the first clause early, even when a longer chunk
would sound marginally better. The first 200 ms of audio buys more perceived quality than any
prosody improvement you could make. This is counterintuitive and it is correct.

### The chunker's edge cases

A naive `split on . ! ?` breaks on:

| Input | Naive result | Correct behaviour |
|---|---|---|
| `Dr. Smith` | splits after "Dr" | don't split on known abbreviations |
| `99.9% uptime` | splits inside the number | don't split between digits |
| `the API...` | three empty chunks | collapse ellipses |
| `He said "yes." Then` | splits inside the quote | close quotes/brackets first |
| `v1.2.3` | splits twice | version-like patterns |
| `e.g. Kafka` | splits after "e.g" | abbreviation list |

Also: **never emit a chunk shorter than ~3 words** unless it is the final one. A one-word
chunk produces a clipped, breathy fragment of audio that sounds broken.

Write unit tests for every row of that table. This is twenty lines of code with a dozen edge
cases, which is exactly the kind of thing to nail with tests rather than by listening.

### Piper

Faster than real time on CPU, no licence cost, dozens of voices, streams cleanly. ~60 MB per
voice. Each persona gets a **fixed voice**, so the counterpart sounds like the same individual
across sessions — a small detail with a large effect on believability.

Watch the sample rate in the voice's `.json` (22050 for the medium/high English voices) and
resample once, server-side, to your chosen downstream rate.

### Gapless playback in the browser

Do **not** use an `<audio>` element. It cannot gaplessly concatenate chunks — you get an
audible click or a small silence between every chunk, which destroys the illusion completely.

Instead, schedule against the Web Audio clock:

```js
let nextStartTime = 0;
function enqueue(audioBuffer) {
  const src = ctx.createBufferSource();
  src.buffer = audioBuffer;
  src.connect(ctx.destination);
  // schedule at the later of "now + jitter buffer" and "end of previous chunk"
  const startAt = Math.max(ctx.currentTime + JITTER, nextStartTime);
  src.start(startAt);
  nextStartTime = startAt + audioBuffer.duration;
  return src;                       // keep the handle so stop-on-speech can kill it
}
```

`ctx.currentTime` is a high-precision clock on the audio thread. Scheduling against it — rather
than `setTimeout` — is what makes the joins inaudible.

### The jitter buffer

A deliberate ~120 ms delay before the first chunk plays, absorbing network variance. Yes, it
costs 120 ms of your budget. It costs less than a stutter, which people notice far more than
120 ms. Grow it adaptively on observed loss; never shrink it below ~60 ms.

### Stop-on-speech

When the user speaks past a short guard interval during playback: stop every scheduled source,
clear the queue, record the persona turn as `truncated`, and return to `listening`.

This is a cheap approximation of barge-in that costs almost nothing and covers the common
case. **True full-duplex barge-in is explicitly out of scope for v1** — it is the single
largest source of complexity in real-time voice and it will eat your window.

---

## 7. Binary WebSocket transport

### Why WebSocket and not WebRTC

WebRTC is the technically correct transport for real-time audio: Opus, jitter buffering,
packet loss concealment and NAT traversal for free. It also brings a signalling server, ICE
and TURN configuration, and a debugging experience that has ended more side projects than any
other single technology.

v1 uses a plain WebSocket carrying binary frames. On normal broadband this costs perhaps
30–60 ms over WebRTC, which the budget absorbs.

**You have already built a WebRTC platform with PeerJS and a custom signalling server**, which
makes you unusually well placed to take that path. The recommendation is still to start with
WebSockets, for one reason: **raw PCM over a socket is trivially inspectable**, and during days
4–8 you will be inspecting audio constantly. Ship the WebSocket version, hit the budget, then
document the WebRTC upgrade as a P1 — at which point *"I migrated the transport and measured
the difference"* is a better story than having started there.

### Frame format

Binary frames need a header, because a bare `ArrayBuffer` carries no context:

```
byte 0      : version (uint8)
byte 1      : kind (uint8)   1 = mic PCM up, 2 = TTS audio down
bytes 2–3   : reserved
bytes 4–7   : seq (uint32 BE)
bytes 8–11  : timestamp_ms (uint32 BE, relative to session start)
bytes 12–   : payload (Int16 PCM LE)
```

12 bytes of overhead on a 640-byte payload is under 2%. Worth every byte: the sequence number
gives you loss detection and resume, and the timestamp gives you client-side clock alignment
for the latency waterfall.

### Backpressure

If the client cannot consume audio as fast as you send it, `ws.send()` buffers in memory and
your server's RSS grows until it dies. Check `bufferedAmount` (client) / the equivalent server
metric, and if it exceeds a threshold, **drop the oldest queued TTS chunk rather than
buffering**. Late audio in a conversation is worthless; audio that arrives on time matters.

### Heartbeats and resume

- Ping every 15 s; if two consecutive pongs are missed, treat the socket as dead.
- On reconnect, the client sends `resume` with the last sequence numbers it saw in both
  directions. The server, which still holds the pinned session, replays anything missed and
  continues. **Ending a session because Wi-Fi hiccupped is a lost recording and a wasted
  fifteen minutes of someone's evening.**

---

## 8. The turn state machine

Formalising this as an explicit state machine — rather than a tangle of callbacks and boolean
flags — is what makes the real-time behaviour **testable**. Every transition is logged with a
timestamp, which is also how the latency dashboard gets built for free.

| State | Behaviour | Exits to |
|---|---|---|
| `idle` | Socket open, VAD running on every frame | `listening` on onset |
| `listening` | Audio buffered, ASR emitting partials, silence timer armed and reset on each voiced frame | `endpointing`, `aborted` |
| `endpointing` | Silence threshold crossed; the §4 cascade runs | `thinking`, or back to `listening` |
| `thinking` | Utterance finalised, persona streaming. Client shows a thinking indicator, **never a spinner** | `speaking` on first chunk |
| `speaking` | Persona audio playing. Microphone still monitored | `idle`, `interrupted` |
| `interrupted` | User spoke past the guard interval. Playback stops, partial turn recorded as truncated | `listening` |
| `closing` | Flush, upload, finalise, enqueue the report job | `closed` |
| `degraded` | A component failed. Session continues reduced | any |

### Why `degraded` is a first-class state

Real-time pipelines **fail partially, not totally**. A TTS request that times out should
produce a spoken fallback and a logged incident — not a dead session and a lost recording.

Modelling degradation explicitly converts the most embarrassing possible demo failure into a
barely noticeable hiccup. It is fifteen lines of code and it is the difference between "the
demo broke" and "you probably didn't notice, but the TTS engine timed out there and it fell
back to the secondary voice."

---

## 9. Instrumenting latency — write this on day 8, not day 22

Every stage on every turn writes a `latency_events` row. **No sampling.**

```python
async with stage(session_id, turn_id, "model_ttft"):
    first_token = await persona.stream().__anext__()
```

Stage names come from a fixed enum: `endpoint_detect`, `asr_finalize`, `prompt_assemble`,
`model_ttft`, `first_chunk_assemble`, `tts_first_chunk`, `transport`, `e2e`.

**Why a table, not a log line.** Latency is the headline claim of this project. A claim you
can only support with `grep` is not an engineering artefact. A claim backed by a queryable
table with p50 and p95 per stage is. When someone asks "which stage dominated and what did you
do about it", you want a query, not a memory.

Writing this on day 8 rather than day 22 also means every optimisation you make on day 11 is
measured rather than guessed.

---

## 10. Pitfalls, ranked by how much time they will cost you

| Pitfall | Symptom | Fix |
|---|---|---|
| Worklet `process()` returns `false` | Audio silently stops | Always `return true` |
| Sample rate mismatch | Chipmunk / demon voice, or gibberish transcripts | Be explicit about the two resample points |
| No `echoCancellation` | System interrupts itself | Enable it; wear headphones |
| `<audio>` element for chunks | Click between every chunk | Web Audio scheduling |
| Allocating inside `process()` | Periodic clicks under GC | Preallocate the ring buffer |
| `condition_on_previous_text=True` | Whisper repeats a phrase 40× | Set it `False` |
| Two VADs (Silero + Whisper's) | Confusing double-gating | `vad_filter=False` in faster-whisper |
| No backpressure handling | Server RSS grows until OOM | Drop old chunks, don't buffer |
| Chunker splits on `99.9%` | Clipped audio mid-number | Test every edge case in §6 |
| Tuning endpointing by feel | Endless fiddling, no progress | Tune against the day-5 labelled set |
| Building the UI before day 8 | Rebuilding it in week three | **The gate exists for this reason** |

---

## 11. The Day 8 gate

> By the end of day 8 you should be able to have a spoken conversation with the system **from
> a terminal** — no interface, no styling, just audio in, audio out, with per-stage timings
> printed.
>
> If that is not true, **do not start the user interface on day 13.** Fix the pipeline.
>
> A beautiful practice room over a voice loop that stutters, cuts people off, or takes four
> seconds to reply is the standard way this project fails, and it is obvious to anyone who
> tries it for thirty seconds.

The CLI harness is ~150 lines. It captures from the system microphone with `sounddevice`,
speaks to the realtime service over the same WebSocket protocol the browser will use, plays
audio back, and prints a stage table after each turn. It is also the thing you will use to
debug for the next three weeks, so make it pleasant.

---

## 12. Interview questions this phase earns you

- *Walk me through your latency budget. Which stage dominated, and what did you do about it?*
- *Why is your end-to-end p95 lower than the sum of your per-stage p95s?*
- *How do you decide the user has finished speaking, and what happens when you get it wrong in
  each direction?*
- *Why AudioWorklet rather than ScriptProcessorNode?*
- *Why WebSocket rather than WebRTC, given you've built WebRTC before?*
- *What happens when the ASR mishears a technical term mid-answer?*
- *Why is `degraded` a state rather than an exception?*

---

## 13. Checklist before Phase 2

- [ ] Browser captures 16 kHz mono PCM through an AudioWorklet with no glitches over 5 minutes
- [ ] Binary protocol frozen and documented in `docs/03-realtime-protocol.md`
- [ ] Silero VAD running on every 20 ms frame
- [ ] **≥200 real utterance boundaries recorded and hand-marked** — this is not optional
- [ ] Streaming ASR emitting partials and finalising with word timestamps; RTF measured
- [ ] Piper synthesising chunk-by-chunk with gapless scheduled playback
- [ ] **A full spoken conversation works from the CLI harness**
- [ ] Per-stage timings printed after every turn and written to `latency_events`

→ `phase-2-LEARN.md`
