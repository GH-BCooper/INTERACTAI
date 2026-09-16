# 0024 — What the `/demo` sample session is, exactly

The spec asks for a pre-recorded session rendered by the real report components. This environment
has no microphone, so a human voice was not available.

**Decision.** The candidate's four answers are scripted (one vague, one rambling, one specific,
one reflective) and synthesized with Piper `en_GB-alan-medium`, a voice no persona uses.
Everything else is real: they were streamed at real-time pace into the running realtime service,
which did VAD, endpointing, ASR, persona generation (Groq `gpt-oss-20b`) and Piper TTS, and
measured latency. The coach worker scored and narrated the session. `scripts/export_demo.py` reads
it back through the API's own serializers. Only turn timings are re-based onto the listener
timeline the recorder assembled; text, scores, evidence spans and word timings are untouched.

Both the demo page and the landing strip say the answers were synthesized. The persona audio is
committed inside one mixed demo MP3. That is a deliberate exception to "never store persona audio":
it is a static public asset, not a user's session.

**Replace this** with a human-voiced session (`scripts/record_demo.py` takes any answer WAVs) before
the recorded video (TASK 6.8).
