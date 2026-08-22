#!/usr/bin/env python3
"""Pre-flight check. Run: uv run python scripts/verify_setup.py"""

import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ok, fail = [], []


def check(name, cond, hint=""):
    (ok if cond else fail).append(f"{name}" + ("" if cond else f"  -> {hint}"))


# Binaries
for b, hint in [
    ("node", "install Node 20"),
    ("pnpm", "corepack enable"),
    ("docker", "install Docker"),
    ("ffmpeg", "apt/brew install ffmpeg"),
]:
    check(f"binary:{b}", shutil.which(b) is not None, hint)

check("python:3.11", sys.version_info[:2] == (3, 11), f"found {sys.version_info[:2]}")

# Env vars
required = [
    "DATABASE_URL",
    "REDIS_URL",
    "GROQ_API_KEY",
    "JWT_SECRET",
    "WS_TOKEN_SECRET",
    "APP_SECRET",
    "S3_BUCKET",
]
for k in required:
    check(f"env:{k}", bool(os.getenv(k)), "missing from .env")
check(
    "secrets distinct",
    len({os.getenv("APP_SECRET"), os.getenv("JWT_SECRET"), os.getenv("WS_TOKEN_SECRET")}) == 3,
    "APP_SECRET, JWT_SECRET and WS_TOKEN_SECRET must differ",
)

# Models on disk
check("model:silero", Path(os.getenv("VAD_MODEL_PATH", "")).exists(), "see §3.1")
piper = Path(os.getenv("PIPER_VOICE_DIR", "./models/piper"))
check("model:piper", piper.exists() and any(piper.glob("*.onnx")), "see §3.3")

# Python packages import
for mod in ["faster_whisper", "onnxruntime", "sqlalchemy", "fastapi", "litellm", "numpy"]:
    try:
        __import__(mod)
        check(f"import:{mod}", True)
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

    litellm.completion(
        model=os.getenv("MODEL_PERSONA"), messages=[{"role": "user", "content": "hi"}], max_tokens=5
    )
    check("groq reachable", True)
except Exception as e:
    check("groq reachable", False, str(e)[:80])

print("\n".join(f"  [ok] {x}" for x in ok))
if fail:
    print("\n".join(f"  [FAIL] {x}" for x in fail))
    sys.exit(1)
print("\nAll checks passed. Go to phase-0-LEARN.md.")
