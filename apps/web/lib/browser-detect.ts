export type DetectedBrowser = "chrome" | "firefox" | "safari" | "other";

/** Task 3.2 edge case: "Mic permission denied -> Browser-specific recovery instructions
 * (Chrome / Firefox / Safari differ, and macOS adds an OS layer)." Order matters: Edge/Chromium
 * report "Chrome" in their UA too, and Chrome's UA also contains "Safari" (WebKit heritage), so
 * Safari must be checked last and specifically for the *absence* of "Chrome"/"Chromium". */
export function detectBrowser(userAgent: string): DetectedBrowser {
  const ua = userAgent.toLowerCase();
  if (ua.includes("firefox")) return "firefox";
  if (ua.includes("chrome") || ua.includes("chromium") || ua.includes("crios")) return "chrome";
  if (ua.includes("safari")) return "safari";
  return "other";
}
