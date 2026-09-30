"use client";

import { ChevronRight, Menu, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { useModKey } from "@/hooks/use-mod-key";
import { useScenario, useSession } from "@/lib/api/hooks";
import type { MeOut } from "@/lib/api/types";
import { useShellStore } from "@/stores/shell-store";

import { ButtonLink } from "../ui/button";
import { UserMenu } from "./user-menu";

interface Crumb {
  label: string;
  href?: string;
}

const SECTION: Record<string, Crumb> = {
  scenarios: { label: "Scenario library", href: "/app/scenarios" },
  sessions: { label: "Session history", href: "/app/sessions" },
  progress: { label: "Progress", href: "/app/progress" },
  settings: { label: "Settings", href: "/app/settings" },
  annotate: { label: "Annotate", href: "/app/annotate" },
  observability: { label: "Observability", href: "/app/observability" },
  evals: { label: "Evaluations", href: "/app/evals" },
};

const SETTINGS_TABS: Record<string, string> = {
  audio: "Audio",
  privacy: "Privacy",
  models: "Models",
};

/** docs/ui-audit-2026-09.md §4: a real trail — section › entity — with the entity's own name
 * (scenario title) once it has loaded. Both lookups hit the TanStack Query cache the page itself
 * already filled, so this costs no extra request on a normal navigation. */
function useBreadcrumbs(pathname: string): Crumb[] {
  const segments = pathname.split("/").filter(Boolean); // ["app", section, id?]
  const section = segments[1];
  const child = segments[2];

  const scenarioId = section === "scenarios" && child && child !== "custom" ? child : undefined;
  const sessionId = section === "sessions" && child ? child : undefined;
  const { data: scenario } = useScenario(scenarioId);
  const { data: session } = useSession(sessionId);
  const { data: sessionScenario } = useScenario(session?.scenario_id);

  if (!section) return [{ label: "Dashboard" }];
  const root = SECTION[section];
  if (!root) return [{ label: "Dashboard", href: "/app" }];
  if (!child) return [{ label: root.label }];

  let leaf: string;
  if (section === "scenarios") leaf = child === "custom" ? "Custom scenario" : (scenario?.title ?? "Scenario");
  else if (section === "sessions") leaf = sessionScenario ? `Report · ${sessionScenario.title}` : "Report";
  else if (section === "settings") leaf = SETTINGS_TABS[child] ?? "Settings";
  else leaf = child;
  return [root, { label: leaf }];
}

export function TopBar({ me }: { me: MeOut }) {
  const pathname = usePathname();
  const openCommandPalette = useShellStore((s) => s.openCommandPalette);
  const setMobileNavOpen = useShellStore((s) => s.setMobileNavOpen);
  const crumbs = useBreadcrumbs(pathname);
  const modKey = useModKey();

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-[var(--bg-page)] px-3 sm:px-4">
      <button
        type="button"
        onClick={() => setMobileNavOpen(true)}
        aria-label="Open navigation"
        className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)] md:hidden"
      >
        <Menu size={18} />
      </button>

      <nav aria-label="Breadcrumb" className="min-w-0">
        <ol className="flex min-w-0 items-center gap-1 text-sm">
          {crumbs.map((c, i) => {
            const last = i === crumbs.length - 1;
            return (
              <Fragment key={`${c.label}-${i}`}>
                {i > 0 && <ChevronRight size={14} aria-hidden className="shrink-0 text-[var(--text-tertiary)]" />}
                <li className={last ? "min-w-0 truncate text-[var(--text-primary)]" : "hidden shrink-0 sm:block"}>
                  {c.href && !last ? (
                    <Link href={c.href} className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
                      {c.label}
                    </Link>
                  ) : (
                    <span aria-current={last ? "page" : undefined}>{c.label}</span>
                  )}
                </li>
              </Fragment>
            );
          })}
        </ol>
      </nav>

      <button
        type="button"
        onClick={openCommandPalette}
        className="ml-2 hidden items-center gap-2 rounded-md border px-3 py-1.5 text-xs text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] lg:flex"
      >
        <Search size={12} aria-hidden />
        Search
        <kbd className="rounded border px-1 font-mono text-xs" suppressHydrationWarning>
          {modKey} K
        </kbd>
      </button>

      <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={openCommandPalette}
          aria-label="Search"
          className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] lg:hidden"
        >
          <Search size={16} />
        </button>
        <ButtonLink href="/app/scenarios" variant="primary" size="sm">
          Start practice
        </ButtonLink>
        <UserMenu me={me} />
      </div>
    </header>
  );
}
