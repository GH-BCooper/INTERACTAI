"""Shared prompt-file loading — mirrors services/realtime/app/persona/minimal.py's
`_load_prompt` (CLAUDE.md §11: prompts are versioned artefacts in content/prompts/, never
string literals in code; every prompt file carries a semantic version in its front matter)."""

from __future__ import annotations

from pathlib import Path

CONTENT_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "content" / "prompts"


def load_prompt(path: Path) -> tuple[str, str]:
    """Returns `(version, prompt_body)`, stripping the YAML front matter."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return "0.0.0", raw.strip()
    _marker, front_matter, body = raw.split("---", 2)
    version = "0.0.0"
    for line in front_matter.splitlines():
        stripped = line.strip()
        if stripped.startswith("version:"):
            version = stripped.split(":", 1)[1].strip().strip('"')
            break
    return version, body.strip()
