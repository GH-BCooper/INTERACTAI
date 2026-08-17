# 01 — SETUP GUIDE

Everything external that must exist before Phase 0 day 1. Budget **one evening**. Doing this
piecemeal during the build is how you lose half of day 6 to a missing API key.

Work top to bottom. Every section ends with a verification command. If a verification fails,
fix it now — none of this gets easier later.

---

## 0. What this project costs

**Zero.** Every component has a working free or self-hosted path, and every free tier has a
named fallback. Nothing in the architecture requires a paid API. If any step in this guide
asks for a credit card, you are on the wrong page — go back and check.

Two things cost money *if you want them* and neither is required: a GPU-hosted persona, and
an always-warm demo. Both have mitigations documented in Phase 6.

---

## 1. Local prerequisites

| Tool | Version | Check | Install |
|---|---|---|---|
| Node.js | ≥ 20.11 LTS | `node -v` | [nodejs.org](https://nodejs.org) or `nvm install 20` |
| pnpm | ≥ 9 | `pnpm -v` | `corepack enable && corepack prepare pnpm@latest --activate` |
| Python | 3.11.x **exactly** | `python3.11 -V` | pyenv, or your distro |
| uv | ≥ 0.4 | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker + Compose v2 | ≥ 24 | `docker compose version` | Docker Desktop / Docker Engine |
| ffmpeg | ≥ 6 | `ffmpeg -version` | `apt install ffmpeg` / `brew install ffmpeg` |
| git | any recent | `git --version` | — |

> **Why Python 3.11 and not 3.12 or 3.13.** `ctranslate2` (the backend under
> `faster-whisper`), `onnxruntime` and the ML stack lag new Python releases by months.
> 3.11 is the version where every wheel in this project exists prebuilt. Using 3.12 will
> work right up until day 6, when you will spend four hours compiling something.

> **Why ffmpeg.** Not for the live path — for dataset work in Phase 5: PCM→Opus encoding,
> resampling recruited-session audio, and generating the fixture set. Install it now.

### Hardware floor

| Resource | Minimum | Comfortable |
|---|---|---|
| RAM | 8 GB | 16 GB |
| CPU | 4 cores | 8 cores |
| Disk | 15 GB free | 30 GB free |
| GPU | none (CPU-only works) | none needed — training runs on Colab |

`faster-whisper base.en` at int8 is ~150 MB resident and runs comfortably below real time on
two cores. If you have less than 4 cores, plan to use `tiny.en` and **report the word error
rate cost rather than hiding it** — that is a better story than a quietly worse model.

### Verify

```bash
node -v && pnpm -v && python3.11 -V && uv --version && \
docker compose version && ffmpeg -version | head -1
```

---

## 2. Accounts and keys

Create these in order. Put every value straight into `.env` as you go — do not "remember to
add it later".

### 2.1 Groq — persona inference (required)

The persona model is chosen on **time to first token**, not benchmark scores, and Groq is
the best free option on that metric.

1. Sign up at `console.groq.com` (GitHub sign-in, no card).
2. **API Keys → Create API Key.** Copy it immediately; it is shown once.
3. `GROQ_API_KEY=gsk_...`

**The binding limit is requests per minute and per day, not tokens.** A single practice
session is roughly 25 short completions, so the daily cap is generous for development.
The fallback when it bites is local Ollama (§3.3).

### 2.2 GitHub OAuth app — sign-in (required)

1. GitHub → Settings → Developer settings → **OAuth Apps → New OAuth App**.
2. Homepage URL: `http://localhost:3000`
3. Authorization callback URL: `http://localhost:8000/auth/github/callback`
4. Generate a client secret.
5. `GITHUB_CLIENT_ID=` / `GITHUB_CLIENT_SECRET=`

You will create a **second** OAuth app later for production with the deployed callback URL.
Do not try to make one app serve both — GitHub allows only one callback per app and you will
break local dev every time you deploy.

### 2.3 Google OAuth — sign-in (required; the audience has both)

1. `console.cloud.google.com` → new project `interactai`.
2. **APIs & Services → OAuth consent screen** → External → fill the minimum → add yourself
   as a test user. You do **not** need to submit for verification; test users are enough.
3. **Credentials → Create Credentials → OAuth client ID → Web application.**
4. Authorised redirect URI: `http://localhost:8000/auth/google/callback`
5. `GOOGLE_CLIENT_ID=` / `GOOGLE_CLIENT_SECRET=`

### 2.4 Neon — managed Postgres with pgvector (required for deploy, optional locally)

Local development uses the Postgres container in Compose. Neon is for the deployed instance.

1. `neon.tech` → sign up → new project, region nearest you.
2. In the SQL editor: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Copy the **pooled** connection string.
4. `DATABASE_URL_PROD=postgresql+asyncpg://...`

Fallback: Supabase free tier, which also ships pgvector.

### 2.5 Upstash — managed Redis (required for deploy)

1. `upstash.com` → Create Database → Regional → free tier.
2. Copy the `rediss://` URL (TLS).
3. `REDIS_URL_PROD=rediss://...`

**The binding limit is daily command count, not memory.** The coach queue handles a few dozen
jobs a day during development, which fits comfortably. Fallback if it ever binds: a
Postgres-backed queue using `SELECT ... FOR UPDATE SKIP LOCKED`, which removes Redis from the
architecture entirely at the cost of some polling latency the coach does not care about.

### 2.6 Object storage — audio artefacts (required for deploy)

Local development uses MinIO in Compose. For production pick one:

**Supabase Storage** (already on your resume, free tier covers this):
- New project → Storage → create bucket `interactai-audio`, **private**.
- Settings → API → copy the URL and the `service_role` key.

**or Cloudflare R2** (the upgrade path if audio volume grows):
- R2 → Create bucket → API Tokens → Object Read & Write.

```
S3_ENDPOINT=          S3_ACCESS_KEY=       S3_SECRET_KEY=
S3_BUCKET=interactai-audio                 S3_REGION=auto
```

> ⚠️ **This is the only free tier that will genuinely bind.** Raw 16 kHz PCM is ~1.9 MB per
> minute; twenty fifteen-minute sessions is ~570 MB, which eats a 1 GB tier before half the
> training set exists. The three mitigations are built into the spec and you must not skip
> them: **never store persona audio** (regenerable from transcript + voice id — this alone
> halves the total), **store Opus not PCM** (24 kbps after transcription, ~12× reduction,
> taking those twenty sessions to under 50 MB), and **expire by default** (30 days, with an
> explicit "keep this one" for sessions that entered the training set).

### 2.7 Hugging Face — Spaces hosting + model downloads (required)

1. `huggingface.co` → sign up.
2. Settings → **Access Tokens** → New token, **write** scope.
3. `HF_TOKEN=hf_...`

Spaces (Docker SDK, free CPU tier: 2 vCPU / 16 GB RAM) is the only genuinely free tier with
enough resident memory to hold Whisper *and* Piper loaded simultaneously. Render's free
instance is too small for a resident Whisper model. You create the actual Space in Phase 6.

### 2.8 Weights & Biases — training run tracking (required for Phase 5)

1. `wandb.ai` → sign up → Settings → copy API key.
2. `WANDB_API_KEY=`

Unlimited for personal projects. This is the artefact that makes the fine-tuning story
credible in an interview — the chart across nine runs is worth more than the final number.

### 2.9 Kaggle or Google Colab — free GPU for the fine-tune (required for Phase 5)

**Kaggle is the better choice**: 30 GPU hours per week, no session-length surprises, and a
DeBERTa-v3-base fine-tune on 1,000 turns takes under twenty minutes on a T4. You are nowhere
near the limit.

1. `kaggle.com` → Settings → **Create New Token** → downloads `kaggle.json`.
2. Settings → **Phone verify** — required to enable GPU. Do this now, not on day 20.

Colab free tier also works; sessions are less predictable.

### 2.10 Sentry — error tracking (optional, 10 minutes, shows operational maturity)

`sentry.io` → new project (Python + Next.js) → copy DSNs → `SENTRY_DSN_API=`, `SENTRY_DSN_WEB=`.

### 2.11 Langfuse — LLM tracing (optional, first on the cut list)

Self-host in Compose or use the cloud free tier. If you use cloud: `langfuse.com` → project →
copy public + secret keys. **Do not spend more than an hour on this.** The `model_calls`
table carries the data that actually matters.

---

## 3. Models to download

Do this **now**, over your good connection. Downloading 400 MB of model weights on day 6 over
a bad connection while trying to debug a streaming decoder is a specific kind of misery.

Create `models/` at the repo root and add it to `.gitignore`. Never commit weights.

### 3.1 Silero VAD (~2 MB)

```bash
mkdir -p models/vad
curl -L -o models/vad/silero_vad.onnx \
  https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx
```

Verify: file is >1 MB and `onnxruntime.InferenceSession` loads it (the setup script does this).

### 3.2 faster-whisper (~150 MB for base.en int8)

Downloads on first use into the HF cache. Pre-pull it:

```bash
uv run python -c "
from faster_whisper import WhisperModel
WhisperModel('base.en', device='cpu', compute_type='int8')
print('base.en cached')
"
```

Also pull `tiny.en` as the automatic-downgrade path for slow hosts.

### 3.3 Piper voices (~60 MB per voice)

Grab two so the persona library has distinct voices from day 7:

```bash
mkdir -p models/piper
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US
curl -L -o models/piper/en_US-lessac-medium.onnx      $BASE/lessac/medium/en_US-lessac-medium.onnx
curl -L -o models/piper/en_US-lessac-medium.onnx.json $BASE/lessac/medium/en_US-lessac-medium.onnx.json
curl -L -o models/piper/en_US-ryan-high.onnx          $BASE/ryan/high/en_US-ryan-high.onnx
curl -L -o models/piper/en_US-ryan-high.onnx.json     $BASE/ryan/high/en_US-ryan-high.onnx.json
```

**Note the sample rate in the `.json`** — `lessac-medium` is 22050 Hz, `ryan-high` is 22050 Hz.
Your capture path is 16 kHz. These are different numbers on purpose and mixing them up is the
single most common Phase 1 bug: it produces audio that plays at the wrong pitch and speed and
sounds like a chipmunk or a demon. The resample point is documented in `phase-1-BUILD.md`.

### 3.4 Ollama — offline persona fallback (strongly recommended)

Guarantees your demo survives a dead conference network or a rate-limited free tier.

```bash
curl -fsSL https://ollama.com/install.sh | sh    # or the macOS/Windows installer
ollama pull qwen2.5:3b-instruct                  # ~2 GB, fast enough on CPU
```

### 3.5 BGE-small embeddings (~130 MB)

```bash
uv run python -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('BAAI/bge-small-en-v1.5')
print('bge-small cached')
"
```

---

## 4. The `.env` template

Create `.env.example` (committed) and `.env` (git-ignored, real values).

```bash
# ─── Core ────────────────────────────────────────────────────────────────
ENVIRONMENT=development
LOG_LEVEL=info
APP_SECRET=                      # openssl rand -hex 32
JWT_SECRET=                      # openssl rand -hex 32 — DIFFERENT from APP_SECRET
WS_TOKEN_SECRET=                 # openssl rand -hex 32 — DIFFERENT again

# ─── URLs ────────────────────────────────────────────────────────────────
WEB_ORIGIN=http://localhost:3000
API_BASE_URL=http://localhost:8000
REALTIME_WS_URL=ws://localhost:8080/ws

# ─── Data ────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://interactai:interactai@localhost:5432/interactai
REDIS_URL=redis://localhost:6379/0

S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=interactai-audio
S3_REGION=us-east-1
S3_FORCE_PATH_STYLE=true         # required for MinIO, false for R2

# ─── Auth ────────────────────────────────────────────────────────────────
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ─── Models: logical roles, never hard-coded providers ───────────────────
GROQ_API_KEY=
MODEL_PERSONA=groq/llama-3.3-70b-versatile
MODEL_PERSONA_LOCAL=ollama/qwen2.5:3b-instruct
MODEL_ENDPOINTER=ollama/qwen2.5:0.5b-instruct
MODEL_NARRATOR=groq/llama-3.3-70b-versatile
MODEL_PLANNER=groq/llama-3.3-70b-versatile
MODEL_JUDGE=groq/llama-3.3-70b-versatile      # evaluation only, never in the user path
MODEL_EMBEDDER=BAAI/bge-small-en-v1.5
OLLAMA_BASE_URL=http://localhost:11434

# ─── Speech ──────────────────────────────────────────────────────────────
ASR_MODEL=base.en
ASR_COMPUTE_TYPE=int8
ASR_DEVICE=cpu
VAD_MODEL_PATH=./models/vad/silero_vad.onnx
PIPER_VOICE_DIR=./models/piper
DEFAULT_PIPER_VOICE=en_US-lessac-medium

# ─── Audio contract — FROZEN ON DAY 4. Changing these is a migration. ────
AUDIO_SAMPLE_RATE=16000
AUDIO_FRAME_MS=20
AUDIO_CHANNELS=1
AUDIO_SAMPLE_FORMAT=pcm_s16le
JITTER_BUFFER_MS=120

# ─── Latency budget (ms) ─────────────────────────────────────────────────
BUDGET_E2E_P50=1100
BUDGET_E2E_P95=1400
ENDPOINT_BASE_SILENCE_MS=500
ENDPOINT_MIN_SILENCE_MS=350
ENDPOINT_MAX_SILENCE_MS=900
ENDPOINT_MIN_UTTERANCE_MS=400
ENDPOINT_MAX_TURN_MS=120000
SEMANTIC_ENDPOINT_TIMEOUT_MS=80

# ─── Budgets ─────────────────────────────────────────────────────────────
MAX_TOKENS_PER_TURN=180
MAX_TOKENS_PER_SESSION=12000
MAX_CENTS_PER_USER_MONTH=200
MAX_CONCURRENT_SESSIONS=4

# ─── Privacy ─────────────────────────────────────────────────────────────
AUDIO_RETENTION_DAYS=30

# ─── Training / tracking (Phase 5) ───────────────────────────────────────
WANDB_API_KEY=
WANDB_PROJECT=interactai-scorer
HF_TOKEN=

# ─── Optional ────────────────────────────────────────────────────────────
SENTRY_DSN_API=
SENTRY_DSN_WEB=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3001
```

Generate the three secrets — **three different values**:

```bash
for k in APP_SECRET JWT_SECRET WS_TOKEN_SECRET; do
  echo "$k=$(openssl rand -hex 32)"
done
```

> **Why three separate secrets.** The WebSocket token is short-lived, scoped to one session,
> and travels in a query string where it can land in proxy logs. If it shares a secret with
> your session JWT, a leaked ws token is a leaked session. Separate secrets make the blast
> radius of that leak exactly one practice session.

---

## 5. Browser and microphone

- **Chrome or Firefox.** Target these for the demo; detect and warn elsewhere. Do not spend
  days on Safari audio quirks in a 24-day window.
- **Use headphones from day 4.** Speaker output feeding back into the microphone will make
  your VAD tuning meaningless and you will chase a ghost for hours.
- `getUserMedia` requires a **secure context**. `http://localhost` counts as secure — but
  `http://192.168.1.x` does not. Testing from your phone on the LAN needs a tunnel
  (`cloudflared tunnel --url http://localhost:3000`) or a local HTTPS cert.
- **Check your OS mic permission too**, not just the browser's. macOS in particular will let
  the browser grant permission while the OS silently returns a stream of zeros.

---

## 6. Verification script

Save as `scripts/verify_setup.py` and run it before Phase 0. It should print all-green.

```python
#!/usr/bin/env python3
"""Pre-flight check. Run: uv run python scripts/verify_setup.py"""
import os, shutil, subprocess, sys
from pathlib import Path

ok, fail = [], []
def check(name, cond, hint=""):
    (ok if cond else fail).append(f"{name}" + ("" if cond else f"  → {hint}"))

# Binaries
for b, hint in [("node","install Node 20"), ("pnpm","corepack enable"),
                ("docker","install Docker"), ("ffmpeg","apt/brew install ffmpeg")]:
    check(f"binary:{b}", shutil.which(b) is not None, hint)

check("python:3.11", sys.version_info[:2] == (3, 11), f"found {sys.version_info[:2]}")

# Env vars
required = ["DATABASE_URL","REDIS_URL","GROQ_API_KEY","JWT_SECRET",
            "WS_TOKEN_SECRET","APP_SECRET","S3_BUCKET"]
for k in required:
    check(f"env:{k}", bool(os.getenv(k)), "missing from .env")
check("secrets distinct",
      len({os.getenv('APP_SECRET'), os.getenv('JWT_SECRET'), os.getenv('WS_TOKEN_SECRET')}) == 3,
      "APP_SECRET, JWT_SECRET and WS_TOKEN_SECRET must differ")

# Models on disk
check("model:silero", Path(os.getenv("VAD_MODEL_PATH","")).exists(), "see §3.1")
piper = Path(os.getenv("PIPER_VOICE_DIR", "./models/piper"))
check("model:piper", piper.exists() and any(piper.glob("*.onnx")), "see §3.3")

# Python packages import
for mod in ["faster_whisper","onnxruntime","sqlalchemy","fastapi","litellm","numpy"]:
    try:
        __import__(mod); check(f"import:{mod}", True)
    except Exception as e:
        check(f"import:{mod}", False, str(e)[:60])

# Silero actually loads
try:
    import onnxruntime as ort
    ort.InferenceSession(os.getenv("VAD_MODEL_PATH"))
    check("silero loads", True)
except Exception as e:
    check("silero loads", False, str(e)[:60])

# Groq reachable
try:
    import litellm
    litellm.completion(model=os.getenv("MODEL_PERSONA"),
                       messages=[{"role":"user","content":"hi"}], max_tokens=5)
    check("groq reachable", True)
except Exception as e:
    check("groq reachable", False, str(e)[:80])

print("\n".join(f"  ✅ {x}" for x in ok))
if fail:
    print("\n".join(f"  ❌ {x}" for x in fail)); sys.exit(1)
print("\nAll checks passed. Go to phase-0-LEARN.md.")
```

---

## 7. Troubleshooting the things that will actually break

| Symptom | Cause | Fix |
|---|---|---|
| `ctranslate2` wheel fails to build | Python 3.12+ | Use 3.11 exactly |
| `onnxruntime` import error on Apple Silicon | wrong wheel | `uv pip install onnxruntime` (not `-silicon`, not `-gpu`) |
| Groq 429 immediately | free-tier RPM | Back off, or flip `MODEL_PERSONA` → `MODEL_PERSONA_LOCAL`. This is exactly why routing is config, not code. |
| Postgres port 5432 in use | local Postgres running | Change the host port in Compose, not the container port |
| MinIO console won't load | wrong port | API is 9000, console is 9001 |
| Mic returns all zeros | OS-level permission | System Settings → Privacy → Microphone |
| Audio plays chipmunk-fast | sample-rate mismatch | Piper is 22050, capture is 16000 — resample, see phase-1 |
| Docker OOM during Whisper load | Desktop memory cap | Raise Docker Desktop RAM to ≥ 6 GB |
| `pgvector` extension missing | fresh Neon DB | `CREATE EXTENSION IF NOT EXISTS vector;` |

---

## 8. Setup complete checklist

- [ ] All binaries verified, Python is 3.11
- [ ] Groq, GitHub OAuth, Google OAuth keys in `.env`
- [ ] Neon + Upstash + storage provisioned (production values in `.env`)
- [ ] HF token, W&B key, Kaggle phone-verified
- [ ] Silero, faster-whisper (base.en **and** tiny.en), two Piper voices, BGE-small downloaded
- [ ] Ollama installed with a 3B instruct model pulled
- [ ] Three distinct secrets generated
- [ ] `verify_setup.py` prints all-green
- [ ] Headphones on your desk

→ `phase-0-LEARN.md`
