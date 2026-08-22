"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useShellStore } from "@/stores/shell-store";
import type { MeOut } from "@/lib/api/types";

import { Button } from "../ui/button";
import { UserMenu } from "./user-menu";

const BREADCRUMB_LABELS: Record<string, string> = {
  app: "Practice library",
  sessions: "Session history",
  settings: "Settings",
};

function useBreadcrumb(pathname: string): string {
  const segments = pathname.split("/").filter(Boolean); // ["app", ...]
  if (segments.length <= 1) return "Practice library";
  const last = segments[segments.length - 1];
  if (last && BREADCRUMB_LABELS[last]) return BREADCRUMB_LABELS[last];
  if (segments[1] === "sessions") return "Report";
  return "InteractAI";
}

export function TopBar({ me }: { me: MeOut }) {
  const pathname = usePathname();
  const openCommandPalette = useShellStore((s) => s.openCommandPalette);
  const crumb = useBreadcrumb(pathname);

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-[var(--bg-page)] px-4">
      <span className="text-sm text-[var(--text-secondary)]">{crumb}</span>

      <button
        type="button"
        onClick={openCommandPalette}
        className="ml-2 hidden items-center gap-2 rounded-md border px-3 py-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)] sm:flex"
      >
        Search
        <kbd className="rounded border px-1 font-mono text-[10px]">⌘K</kbd>
      </button>

      <div className="ml-auto flex items-center gap-3">
        <Link href="/app">
          <Button variant="primary" size="sm">
            Start practice
          </Button>
        </Link>
        <UserMenu me={me} />
      </div>
    </header>
  );
}
