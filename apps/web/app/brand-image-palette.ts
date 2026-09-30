/**
 * The only raw colour values in app/ — and deliberately so. `opengraph-image.tsx` and
 * `apple-icon.tsx` are rendered to PNG by Satori (next/og) at build time, where CSS custom
 * properties do not exist, so they cannot read the tokens in globals.css. These are copies of the
 * dark-theme tokens they stand for; keep them in step with globals.css. scripts/check-design-tokens
 * .mjs exempts this one file by name for exactly this reason.
 */
export const BRAND = {
  bgPage: "#0b0d10",
  bgCard: "#14171b",
  border: "#2a2f36",
  textPrimary: "#e8eaed",
  textSecondary: "#9aa1ab",
  accent: "#5b8cff",
} as const;
