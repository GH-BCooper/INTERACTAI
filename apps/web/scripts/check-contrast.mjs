#!/usr/bin/env node
/**
 * WCAG 2.1 contrast gate over the design tokens in app/globals.css.
 *
 * Why this exists as a check and not a review note: `check-design-tokens.mjs` already enforces
 * that components use tokens instead of raw hex, which makes the palette the single place a
 * contrast mistake can live — and nothing was reading the palette. An audit on 2026-09-28 found
 * eight failing pairs shipped, including white-on-`--accent` at 3.16:1, which is the label on the
 * primary call-to-action button on the landing page, the sign-in page and every `Button` with
 * `variant="primary"`. The dark theme is the default, so that was the first thing most visitors
 * saw. `--text-tertiary` (every timestamp and metadata line) was at 3.39:1 on `--bg-raised`, and
 * `--score-insufficient` — the "not enough signal" state CLAUDE.md §6 makes load-bearing — at
 * 3.72:1.
 *
 * Contrast is arithmetic on the token values, so it is checkable. Run via `pnpm run lint`.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// fileURLToPath, not `.pathname` — this repo's path contains a space, which a URL
// percent-encodes and `readFileSync` then cannot find.
const CSS = fileURLToPath(new URL("../app/globals.css", import.meta.url));
const css = readFileSync(CSS, "utf8");

/** The palette blocks, by the selector that opens each one, and the theme each defines. */
const BLOCKS = [
  { marker: ":root {", theme: "dark (default)" },
  { marker: "@media (prefers-color-scheme: light) {", theme: "light (prefers-color-scheme)" },
  { marker: ':root[data-theme="light"] {', theme: "light (explicit)" },
  { marker: ':root[data-theme="dark"] {', theme: "dark (explicit)" },
];

/**
 * Foreground/background pairs the UI actually renders, with the WCAG threshold each must meet.
 * 4.5 is AA for normal-size text; 3.0 is AA for non-text UI affordances (focus rings). Add a row
 * here whenever a new token pair starts appearing together in a component.
 */
const PAIRS = [
  ["text-primary", "bg-page", 4.5],
  ["text-primary", "bg-card", 4.5],
  ["text-primary", "bg-raised", 4.5],
  ["text-secondary", "bg-page", 4.5],
  ["text-secondary", "bg-card", 4.5],
  ["text-secondary", "bg-raised", 4.5],
  ["text-tertiary", "bg-page", 4.5],
  ["text-tertiary", "bg-card", 4.5],
  ["text-tertiary", "bg-raised", 4.5],
  ["accent", "bg-page", 4.5],
  ["accent", "bg-card", 4.5],
  ["accent-hover", "bg-card", 4.5],
  // Button labels. `--text-on-accent` is used on both accent and danger backgrounds.
  ["text-on-accent", "accent", 4.5],
  ["text-on-accent", "accent-hover", 4.5],
  ["text-on-accent", "danger", 4.5],
  ["text-on-accent", "danger-hover", 4.5],
  ["accent-contrast", "accent", 4.5],
  ["danger", "bg-page", 4.5],
  ["danger", "bg-card", 4.5],
  ["danger-hover", "bg-card", 4.5],
  // The four reserved rubric-value colours, on every surface a score is rendered on.
  ["score-strong", "bg-page", 4.5],
  ["score-strong", "bg-card", 4.5],
  ["score-strong", "bg-raised", 4.5],
  ["score-developing", "bg-page", 4.5],
  ["score-developing", "bg-card", 4.5],
  ["score-developing", "bg-raised", 4.5],
  ["score-weak", "bg-page", 4.5],
  ["score-weak", "bg-card", 4.5],
  ["score-weak", "bg-raised", 4.5],
  ["score-insufficient", "bg-page", 4.5],
  ["score-insufficient", "bg-card", 4.5],
  ["score-insufficient", "bg-raised", 4.5],
  // Status indicators (mic check, BYOK key test, trend arrows) — see globals.css on why
  // these are not the reserved --score-* tokens.
  ["status-ok", "bg-page", 4.5],
  ["status-ok", "bg-card", 4.5],
  ["status-ok", "bg-raised", 4.5],
  ["status-bad", "bg-page", 4.5],
  ["status-bad", "bg-card", 4.5],
  ["status-bad", "bg-raised", 4.5],
  ["focus-ring", "bg-page", 3.0],
  ["focus-ring", "bg-card", 3.0],
  ["focus-ring", "bg-raised", 3.0],
];

function paletteAt(marker) {
  const start = css.indexOf(marker);
  if (start === -1) throw new Error(`globals.css no longer contains the block "${marker}"`);
  const end = css.indexOf("\n}", start);
  const palette = {};
  for (const m of css.slice(start, end).matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})\b/g)) {
    palette[m[1]] = m[2];
  }
  return palette;
}

const channel = (v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a, b) {
  const [la, lb] = [luminance(a), luminance(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const failures = [];
let checked = 0;

for (const { marker, theme } of BLOCKS) {
  const palette = paletteAt(marker);
  for (const [fg, bg, min] of PAIRS) {
    if (!(fg in palette) || !(bg in palette)) {
      const missing = fg in palette ? bg : fg;
      failures.push(`[${theme}] --${missing} is not defined in this block, but a pair needs it`);
      continue;
    }
    checked += 1;
    const ratio = contrast(palette[fg], palette[bg]);
    if (ratio < min) {
      failures.push(
        `[${theme}] --${fg} (${palette[fg]}) on --${bg} (${palette[bg]}): ` +
          `${ratio.toFixed(2)}:1 — needs ${min.toFixed(1)}:1`
      );
    }
  }
}

if (failures.length > 0) {
  console.error("Contrast check failed:\n");
  for (const f of failures) console.error(`  ✗ ${f}`);
  console.error(`\n${failures.length} of ${checked} token pair(s) below their WCAG threshold.`);
  process.exit(1);
}

console.log(`Contrast check passed: ${checked} token pairs, all at or above WCAG AA.`);
