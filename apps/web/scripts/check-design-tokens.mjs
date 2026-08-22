#!/usr/bin/env node
/**
 * docs/phase-3-BUILD.md TASK 3.1 acceptance criteria, enforced by grep rather than review:
 *
 *   - "a lint rule or CI grep fails if a raw hex colour appears in a component"
 *   - "Score colours appear only in rubric-value contexts (grep-verified)"
 *
 * Run via `pnpm run lint` (chained after eslint) — see package.json.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const SCAN_DIRS = ["app", "components", "hooks"];
const EXTENSIONS = new Set([".ts", ".tsx"]);
const HEX_COLOR = /#[0-9a-fA-F]{3,8}\b/g;
const SCORE_TOKENS = /--score-(strong|developing|weak|insufficient)\b/g;

// The one place score colour tokens may be consumed outside app/globals.css itself — a
// dedicated, narrow directory so "is this a rubric-value context" is a path check, not a
// judgement call at review time.
const SCORE_TOKEN_ALLOWED_DIR = join(ROOT, "components", "score");

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next") continue;
    const full = join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) walk(full, out);
    else if (EXTENSIONS.has(extname(name))) out.push(full);
  }
}

let failures = [];

for (const dir of SCAN_DIRS) {
  const abs = join(ROOT, dir);
  let files = [];
  try {
    walk(abs, files);
  } catch {
    continue; // directory doesn't exist yet
  }

  for (const file of files) {
    const text = readFileSync(file, "utf8");

    for (const match of text.matchAll(HEX_COLOR)) {
      failures.push(`${file}: raw hex colour "${match[0]}" — use a design token instead`);
    }

    if (!file.startsWith(SCORE_TOKEN_ALLOWED_DIR)) {
      for (const match of text.matchAll(SCORE_TOKENS)) {
        failures.push(
          `${file}: score colour token "${match[0]}" used outside components/score/ — ` +
            "these four variables are reserved for rubric values only"
        );
      }
    }
  }
}

if (failures.length > 0) {
  console.error("Design token check failed:\n");
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(`\n${failures.length} violation(s).`);
  process.exit(1);
}

console.log("Design token check passed: no raw hex colours, score colours properly scoped.");
