"use client";

import { clsx } from "clsx";
import { History, LayoutGrid, PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useShellStore } from "@/stores/shell-store";

const NAV_ITEMS = [
  { href: "/app", label: "Practice library", icon: LayoutGrid },
  { href: "/app/sessions", label: "Session history", icon: History },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

interface SidebarProps {
  practiceMinutesThisWeek: number;
}

/** Task 3.1: "Collapsible left sidebar with primary nav and a practice-minutes-this-week meter
 * pinned at the bottom." Not present on the practice room route — this component only ever
 * renders inside app/app/(shell)/layout.tsx. */
export function Sidebar({ practiceMinutesThisWeek }: SidebarProps) {
  const collapsed = useShellStore((s) => s.sidebarCollapsed);
  const toggle = useShellStore((s) => s.toggleSidebar);
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className={clsx(
        "flex h-dvh shrink-0 flex-col border-r bg-[var(--bg-card)] transition-[width] duration-200",
        collapsed ? "w-16" : "w-56",
      )}
    >
      <div className="flex h-14 items-center justify-between px-3">
        {!collapsed && <span className="text-sm font-medium">InteractAI</span>}
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="ml-auto flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]"
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <ul className="flex flex-1 flex-col gap-1 px-2 py-2">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-[var(--bg-raised)] font-medium text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]",
                )}
              >
                <Icon size={16} className="shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="border-t px-3 py-3">
        {collapsed ? (
          <div
            className="mx-auto h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
            title={`${practiceMinutesThisWeek} min practiced this week`}
          />
        ) : (
          <div>
            <p className="text-xs text-[var(--text-tertiary)]">This week</p>
            <p className="mt-0.5 font-mono text-sm">{practiceMinutesThisWeek} min practiced</p>
          </div>
        )}
      </div>
    </nav>
  );
}
