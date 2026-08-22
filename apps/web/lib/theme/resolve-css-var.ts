/** Bridges a CSS custom property (app/globals.css) into contexts that sit outside the CSS
 * cascade and can never resolve `var(...)` themselves — specifically wavesurfer.js's
 * `<canvas>` rendering (components/report/waveform.tsx). Reads the value live from computed
 * style, so it automatically tracks the current theme; callers that need to react to a theme
 * change (not just read it once at mount) should re-call this after the change, not cache it. */
export function resolveCssVar(name: string, fallback = "#888888"): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}
