"use client";

import { useEffect, useState } from "react";

import { isApplePlatform } from "@/lib/platform";

/** The modifier label for shortcut hints. Starts as "Ctrl" on the server and first client render
 * (no hydration mismatch), then corrects to "⌘" on Apple platforms. */
export function useModKey(): string {
  const [label, setLabel] = useState("Ctrl");
  useEffect(() => {
    if (isApplePlatform()) setLabel("⌘");
  }, []);
  return label;
}
