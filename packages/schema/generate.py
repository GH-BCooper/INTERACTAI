#!/usr/bin/env python3
"""Regenerate Pydantic models from ws-messages.schema.json. Run via `make schema`.

Output: services/realtime/app/schemas/ws.py — the realtime service is the only process that
speaks the WebSocket protocol directly (CLAUDE.md §2, "api ... never touches audio").

Deterministic: two consecutive runs produce byte-identical output (no embedded timestamp).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = REPO_ROOT / "packages" / "schema" / "ws-messages.schema.json"
OUTPUT_FILE = REPO_ROOT / "services" / "realtime" / "app" / "schemas" / "ws.py"

HEADER = (
    "# GENERATED — DO NOT EDIT. Run `make schema`.\n"
    "#\n"
    "# Source: packages/schema/ws-messages.schema.json\n"
    "# Generator: packages/schema/generate.py -> datamodel-code-generator"
)


def main() -> int:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "datamodel_code_generator",
        "--input",
        str(SCHEMA_FILE),
        "--input-file-type",
        "jsonschema",
        "--output-model-type",
        "pydantic_v2.BaseModel",
        "--target-python-version",
        "3.11",
        "--output",
        str(OUTPUT_FILE),
        "--use-annotated",
        "--use-standard-collections",
        "--use-union-operator",
        "--field-constraints",
        "--enum-field-as-literal",
        "one",
        "--class-name",
        "WsEnvelope",
        "--use-title-as-name",
        "--disable-timestamp",
        "--custom-file-header",
        HEADER,
        "--custom-file-header-mode",
        "replace",
        "--formatters",
        "ruff-check",
        "ruff-format",
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)  # noqa: S603 — fixed argv, no shell, no user input
    if result.returncode != 0:
        print("datamodel-code-generator failed", file=sys.stderr)
        return result.returncode

    print(f"wrote {OUTPUT_FILE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
