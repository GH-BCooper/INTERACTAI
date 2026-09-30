"use client";

import { Command } from "cmdk";
import {
  Activity,
  AudioLines,
  ClipboardCheck,
  FlaskConical,
  History,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  Moon,
  Play,
  Repeat,
  Shield,
  TrendingUp,
  User,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { ScoreBadge } from "@/components/score/score-badge";
import { Dialog } from "@/components/ui/dialog";
import { capitalize } from "@/components/ui/primitives";
import { useMe, useScenarios, useSessions } from "@/lib/api/hooks";
import { useShellStore } from "@/stores/shell-store";
import { useThemeStore } from "@/stores/theme-store";

const ITEM_CLASS =
  "flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-[var(--text-primary)] data-[selected=true]:bg-[var(--bg-raised)]";
const GROUP_CLASS =
  "px-1 py-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-[var(--text-tertiary)]";

function Item({
  icon: Icon,
  children,
  hint,
  value,
  onSelect,
}: {
  icon: LucideIcon;
  children: ReactNode;
  hint?: ReactNode;
  value?: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item value={value} onSelect={onSelect} className={ITEM_CLASS}>
      <Icon size={16} aria-hidden className="shrink-0 text-[var(--text-tertiary)]" />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {hint && <span className="shrink-0 text-xs text-[var(--text-tertiary)]">{hint}</span>}
    </Command.Item>
  );
}

const NAVIGATION: { label: string; href: string; icon: LucideIcon; keywords?: string }[] = [
  { label: "Dashboard", href: "/app", icon: LayoutDashboard, keywords: "home" },
  { label: "Scenario library", href: "/app/scenarios", icon: LayoutGrid, keywords: "practice browse" },
  { label: "Session history", href: "/app/sessions", icon: History, keywords: "reports past" },
  { label: "Progress", href: "/app/progress", icon: TrendingUp, keywords: "trends scores" },
  { label: "Settings · Profile", href: "/app/settings", icon: User, keywords: "resume role" },
  { label: "Settings · Audio", href: "/app/settings/audio", icon: AudioLines, keywords: "microphone speaker captions" },
  { label: "Settings · Privacy", href: "/app/settings/privacy", icon: Shield, keywords: "export delete consent retention" },
  { label: "Settings · Models", href: "/app/settings/models", icon: KeyRound, keywords: "api key groq byok" },
];

const ADMIN_NAVIGATION = [
  { label: "Annotate", href: "/app/annotate", icon: ClipboardCheck },
  { label: "Observability", href: "/app/observability", icon: Activity },
  { label: "Evaluations", href: "/app/evals", icon: FlaskConical },
];

/** Task 3.1: "Command palette (⌘K): fuzzy search across scenarios, sessions and settings, plus
 * verbs — start session, repeat last scenario, toggle theme." `cmdk` provides the fuzzy match
 * and keyboard navigation; everything here is wiring results to navigation. Kept mounted and
 * animated through the shared Dialog (docs/ui-audit-2026-09.md §4). */
export function CommandPalette() {
  const open = useShellStore((s) => s.commandPaletteOpen);
  const openPalette = useShellStore((s) => s.openCommandPalette);
  const closePalette = useShellStore((s) => s.closeCommandPalette);
  const toggleTheme = useThemeStore((s) => s.toggle);
  const router = useRouter();

  const { data: me } = useMe();
  const { data: scenarios } = useScenarios();
  const { data: recentSessions } = useSessions({ limit: 5 });

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (useShellStore.getState().commandPaletteOpen) closePalette();
        else openPalette();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [openPalette, closePalette]);

  const lastScenarioId = recentSessions?.items[0]?.scenario_id;

  function go(path: string) {
    closePalette();
    router.push(path);
  }

  return (
    <Dialog open={open} onClose={closePalette} position="top" className="max-w-lg overflow-hidden p-0">
      <Command label="Command palette" shouldFilter loop>
        <Command.Input
          autoFocus
          placeholder="Search scenarios, sessions, settings…"
          className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none placeholder:text-[var(--text-tertiary)]"
        />
        <Command.List className="max-h-[min(24rem,60vh)] overflow-y-auto p-1">
          <Command.Empty className="px-4 py-6 text-center text-sm text-[var(--text-tertiary)]">No results.</Command.Empty>

          <Command.Group heading="Actions" className={GROUP_CLASS}>
            <Item icon={Play} onSelect={() => go("/app/scenarios")}>
              Start a new session
            </Item>
            {lastScenarioId && (
              <Item icon={Repeat} onSelect={() => go(`/app/scenarios?scenario=${lastScenarioId}`)}>
                Repeat last scenario
              </Item>
            )}
            <Item
              icon={Moon}
              onSelect={() => {
                toggleTheme();
                closePalette();
              }}
            >
              Toggle theme
            </Item>
          </Command.Group>

          <Command.Group heading="Go to" className={GROUP_CLASS}>
            {NAVIGATION.map((n) => (
              <Item key={n.href} icon={n.icon} value={`${n.label} ${n.keywords ?? ""}`} onSelect={() => go(n.href)}>
                {n.label}
              </Item>
            ))}
            {me?.user.is_admin &&
              ADMIN_NAVIGATION.map((n) => (
                <Item key={n.href} icon={n.icon} value={`${n.label} admin`} hint="Admin" onSelect={() => go(n.href)}>
                  {n.label}
                </Item>
              ))}
          </Command.Group>

          {recentSessions && recentSessions.items.length > 0 && (
            <Command.Group heading="Recent sessions" className={GROUP_CLASS}>
              {recentSessions.items.map((s) => (
                <Item
                  key={s.id}
                  icon={History}
                  value={`session ${s.scenario_title} ${s.scenario_family ?? ""} ${s.id}`}
                  hint={s.status === "closed" ? <ScoreBadge score={s.overall_score} /> : "In progress"}
                  onSelect={() => go(s.status === "closed" ? `/app/sessions/${s.id}` : `/app/practice/${s.id}`)}
                >
                  {s.scenario_title}
                </Item>
              ))}
            </Command.Group>
          )}

          {scenarios && scenarios.length > 0 && (
            <Command.Group heading="Scenarios" className={GROUP_CLASS}>
              {scenarios.map((s) => (
                <Item
                  key={s.id}
                  icon={LayoutGrid}
                  value={`${s.title} ${s.family} ${s.difficulty} ${s.tags.join(" ")}`}
                  hint={`${capitalize(s.family)} · ${capitalize(s.difficulty)}`}
                  onSelect={() => go(`/app/scenarios?scenario=${s.id}`)}
                >
                  {s.title}
                </Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
        <div className="flex items-center gap-4 border-t px-4 py-2 text-xs text-[var(--text-tertiary)]">
          <span>
            <kbd className="font-mono">↑↓</kbd> move
          </span>
          <span>
            <kbd className="font-mono">↵</kbd> open
          </span>
          <span>
            <kbd className="font-mono">Esc</kbd> close
          </span>
        </div>
      </Command>
    </Dialog>
  );
}
