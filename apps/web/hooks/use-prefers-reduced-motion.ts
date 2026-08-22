"use client";

import { useEffect, useState } from "react";

/** Task 3.2 acceptance criterion: "Reduced-motion mode replaces the ring with a static
 * indicator." The CSS-only continuous animations already respect the media query
 * (app/globals.css), but the amplitude ring's requestAnimationFrame loop is JS-driven and has
 * to check this explicitly to stop scheduling frames at all, not just animate to a no-op. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mql.matches);
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
