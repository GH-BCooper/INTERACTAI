"""First-boot model fetch for the realtime image (Phase 6 TASK 6.4a).

Weights are never baked into an image layer; this downloads any missing file into the mounted
/models volume and is a no-op on every later boot. faster-whisper fetches its own weights into
HF_HOME (also on the volume) the first time the ASR model loads.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en"
VOICES = {
    "en_US-lessac-medium": "en_US/lessac/medium",
    "en_US-ryan-medium": "en_US/ryan/medium",
}
SILERO_URL = "https://github.com/snakers4/silero-vad/raw/v5.1.2/src/silero_vad/data/silero_vad.onnx"


def _fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"fetching {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as out:  # noqa: S310
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.rename(dest)


def main() -> int:
    vad_path = Path(os.environ.get("VAD_MODEL_PATH", "/models/vad/silero_vad.onnx"))
    voice_dir = Path(os.environ.get("PIPER_VOICE_DIR", "/models/piper"))
    _fetch(SILERO_URL, vad_path)
    for voice, sub in VOICES.items():
        for suffix in (".onnx", ".onnx.json"):
            _fetch(f"{PIPER_BASE}/{sub}/{voice}{suffix}", voice_dir / f"{voice}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
