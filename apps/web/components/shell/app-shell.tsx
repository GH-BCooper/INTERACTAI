"use client";

import type { ReactNode } from "react";

import { useMe } from "@/lib/api/hooks";

import { CommandPalette } from "./command-palette";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";

function ShellSkeleton() {
  return (
    <div className="flex h-dvh w-full">
      <div className="h-full w-56 shrink-0 animate-pulse border-r bg-[var(--bg-card)]" />
      <div className="flex flex-1 flex-col">
        <div className="h-14 shrink-0 animate-pulse border-b bg-[var(--bg-page)]" />
        <div className="flex-1 bg-[var(--bg-page)]" />
      </div>
    </div>
  );
}

/** Every authenticated page except the practice room (Task 3.1) — sidebar, top bar, command
 * palette. AuthGate (the parent /app/layout.tsx) already guarantees a token exists by the time
 * this mounts, so `useMe` here is just fetching profile data, not re-checking auth. */
export function AppShell({ children }: { children: ReactNode }) {
  const { data: me, isPending } = useMe();

  if (isPending || !me) return <ShellSkeleton />;

  return (
    <div className="flex h-dvh w-full overflow-hidden">
      <Sidebar
        practiceMinutesThisWeek={me.practice_minutes_this_week}
        isAdmin={me.user.is_admin}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar me={me} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
