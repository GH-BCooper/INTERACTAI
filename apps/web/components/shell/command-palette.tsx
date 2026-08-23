"use client";

import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useScenarios, useSessions } from "@/lib/api/hooks";
import { useShellStore } from "@/stores/shell-store";
import { useThemeStore } from "@/stores/theme-store";

/** Task 3.1: "Command palette (⌘K): fuzzy search across scenarios, sessions and settings, plus
 * verbs — start session, repeat last scenario, toggle theme." `cmdk` provides the fuzzy match
 * and keyboard navigation; everything here is just wiring results to navigation. */
export function CommandPalette() {
  const open = useShellStore((s) => s.commandPaletteOpen);
  const openPalette = useShellStore((s) => s.openCommandPalette);
  const closePalette = useShellStore((s) => s.closeCommandPalette);
  const toggleTheme = useThemeStore((s) => s.toggle);
  const router = useRouter();

  const { data: scenarios } = useScenarios();
  const { data: recentSessions } = useSessions({ limit: 5 });

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) closePalette();
        else openPalette();
      } else if (e.key === "Escape" && open) {
        closePalette();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, openPalette, closePalette]);

  if (!open) return null;

  const lastScenarioId = recentSessions?.items[0]?.scenario_id;

  function go(path: string) {
    closePalette();
    router.push(path);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[15vh]"
      onClick={closePalette}
    >
      <Command
        label="Command palette"
        className="w-full max-w-lg overflow-hidden rounded-lg border bg-[var(--bg-card)] shadow-none"
        onClick={(e) => e.stopPropagation()}
        shouldFilter
      >
        <Command.Input
          autoFocus
          placeholder="Search scenarios, sessions, settings…"
          className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none placeholder:text-[var(--text-tertiary)]"
        />
        <Command.List className="max-h-80 overflow-y-auto p-1">
          <Command.Empty className="px-4 py-6 text-center text-sm text-[var(--text-tertiary)]">
            No results.
          </Command.Empty>

          <Command.Group heading="Actions" className="px-2 py-1 text-xs text-[var(--text-tertiary)]">
            <Command.Item
              onSelect={() => go("/app/scenarios")}
              className="cursor-pointer rounded px-2 py-2 text-sm data-[selected=true]:bg-[var(--bg-raised)]"
            >
              Start a new session
            </Command.Item>
            {lastScenarioId && (
              <Command.Item
                onSelect={() => go(`/app/scenarios?scenario=${lastScenarioId}`)}
                className="cursor-pointer rounded px-2 py-2 text-sm data-[selected=true]:bg-[var(--bg-raised)]"
              >
                Repeat last scenario
              </Command.Item>
            )}
            <Command.Item
              onSelect={() => {
                toggleTheme();
                closePalette();
              }}
              className="cursor-pointer rounded px-2 py-2 text-sm data-[selected=true]:bg-[var(--bg-raised)]"
            >
              Toggle theme
            </Command.Item>
            <Command.Item
              onSelect={() => go("/app/settings")}
              className="cursor-pointer rounded px-2 py-2 text-sm data-[selected=true]:bg-[var(--bg-raised)]"
            >
              Open settings
            </Command.Item>
          </Command.Group>

          {scenarios && scenarios.length > 0 && (
            <Command.Group heading="Scenarios" className="px-2 py-1 text-xs text-[var(--text-tertiary)]">
              {scenarios.map((s) => (
                <Command.Item
                  key={s.id}
                  value={`${s.title} ${s.family} ${s.difficulty}`}
                  onSelect={() => go(`/app/scenarios?scenario=${s.id}`)}
                  className="cursor-pointer rounded px-2 py-2 text-sm data-[selected=true]:bg-[var(--bg-raised)]"
                >
                  {s.title}
                  <span className="ml-2 text-xs text-[var(--text-tertiary)]">
                    {s.family} · {s.difficulty}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {recentSessions && recentSessions.items.length > 0 && (
            <Command.Group heading="Recent sessions" className="px-2 py-1 text-xs text-[var(--text-tertiary)]">
              {recentSessions.items.map((s) => (
                <Command.Item
                  key={s.id}
                  value={`session ${s.id}`}
                  onSelect={() => go(`/app/sessions/${s.id}`)}
                  className="cursor-pointer rounded px-2 py-2 text-sm data-[selected=true]:bg-[var(--bg-raised)]"
                >
                  Session from {new Date(s.created_at).toLocaleDateString()}
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  );
}
