"use client";

import { Star } from "lucide-react";
import { useEffect, useState } from "react";

export const REPO = "GH-BCooper/INTERACTAI";

/** Live star count, fetched client-side after paint so it never blocks the hero. Shows nothing
 * rather than a guessed number if the GitHub API is unreachable or rate-limited. */
export function GitHubStars() {
  const [stars, setStars] = useState<number | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    fetch(`https://api.github.com/repos/${REPO}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { stargazers_count?: number } | null) => {
        if (d && typeof d.stargazers_count === "number") setStars(d.stargazers_count);
      })
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);
  if (stars === null) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded bg-[var(--bg-raised)] px-1.5 py-0.5 font-mono text-xs">
      <Star size={11} aria-hidden /> {stars.toLocaleString()}
    </span>
  );
}
