"use client";

import { clsx } from "clsx";
import {
  Activity,
  ClipboardCheck,
  FlaskConical,
  History,
  LayoutDashboard,
  LayoutGrid,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  TrendingUp,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { Wordmark } from "@/components/ui/logo";
import { useShellStore } from "@/stores/shell-store";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/app", label: "Dashboard", icon: LayoutDashboard },
  { href: "/app/scenarios", label: "Scenario library", icon: LayoutGrid },
  { href: "/app/sessions", label: "Session history", icon: History },
  { href: "/app/progress", label: "Progress", icon: TrendingUp },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

// docs/phase-5-BUILD.md TASK 5.3a: "/app/annotate (admin only)." Only ever rendered when
// `isAdmin` is true — the route itself re-checks server-side regardless (AdminUser dependency),
// this is purely so a non-admin never sees a link to a tool that would 403 them.
export const ADMIN_NAV_ITEMS: NavItem[] = [
  { href: "/app/annotate", label: "Annotate", icon: ClipboardCheck },
  // Phase 6 TASK 6.1/6.2.
  { href: "/app/observability", label: "Observability", icon: Activity },
  { href: "/app/evals", label: "Evaluations", icon: FlaskConical },
];

interface SidebarProps {
  practiceMinutesThisWeek: number;
  isAdmin: boolean;
}

function isActive(pathname: string, href: string): boolean {
  return href === "/app" ? pathname === "/app" : pathname.startsWith(href);
}

function NavList({ items, collapsed, pathname, onNavigate }: { items: NavItem[]; collapsed: boolean; pathname: string; onNavigate?: () => void }) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              // Collapsed, the label is gone — the tooltip and the accessible name carry it.
              title={collapsed ? item.label : undefined}
              aria-label={collapsed ? item.label : undefined}
              className={clsx(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150",
                collapsed && "justify-center px-0",
                active
                  ? "bg-[var(--bg-raised)] font-medium text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]",
              )}
            >
              <Icon size={16} className="shrink-0" aria-hidden />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function SidebarBody({
  collapsed,
  practiceMinutesThisWeek,
  isAdmin,
  pathname,
  onNavigate,
}: SidebarProps & { collapsed: boolean; pathname: string; onNavigate?: () => void }) {
  return (
    <>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        <NavList items={NAV_ITEMS} collapsed={collapsed} pathname={pathname} onNavigate={onNavigate} />
        {isAdmin && (
          <div className="mt-4 border-t pt-3">
            {!collapsed && (
              <p className="px-3 pb-1 text-xs text-[var(--text-tertiary)]" id="admin-nav-label">
                Admin
              </p>
            )}
            <nav aria-label="Admin">
              <NavList items={ADMIN_NAV_ITEMS} collapsed={collapsed} pathname={pathname} onNavigate={onNavigate} />
            </nav>
          </div>
        )}
      </div>

      <div className="border-t px-3 py-3">
        {collapsed ? (
          <div
            className="mx-auto flex h-6 w-6 items-center justify-center rounded-full border font-mono text-xs text-[var(--text-secondary)]"
            title={`${practiceMinutesThisWeek} min practised this week`}
          >
            <span className="sr-only">{practiceMinutesThisWeek} minutes practised this week</span>
            <span aria-hidden>{practiceMinutesThisWeek > 99 ? "99+" : practiceMinutesThisWeek}</span>
          </div>
        ) : (
          // No weekly goal exists on the profile, so this stays a measured number — a progress
          // bar against an invented target would be a fabricated metric (CLAUDE.md §1.10).
          <div>
            <p className="text-xs text-[var(--text-tertiary)]">This week</p>
            <p className="mt-0.5 font-mono text-sm">{practiceMinutesThisWeek} min practised</p>
          </div>
        )}
      </div>
    </>
  );
}

/** Task 3.1: "Collapsible left sidebar with primary nav and a practice-minutes-this-week meter
 * pinned at the bottom." From `md` up it is a rail (collapsed state persisted, `[` toggles it);
 * below `md` it is a drawer opened from the top bar (docs/ui-audit-2026-09.md §1.6). Not present
 * on the practice room route — this only renders inside app/app/(shell)/layout.tsx. */
export function Sidebar({ practiceMinutesThisWeek, isAdmin }: SidebarProps) {
  const collapsed = useShellStore((s) => s.sidebarCollapsed);
  const toggle = useShellStore((s) => s.toggleSidebar);
  const mobileOpen = useShellStore((s) => s.mobileNavOpen);
  const setMobileOpen = useShellStore((s) => s.setMobileNavOpen);
  const pathname = usePathname();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, select, [contenteditable='true']");
      if (e.key === "[" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        toggle();
      } else if (e.key === "Escape" && mobileOpen) {
        setMobileOpen(false);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [toggle, mobileOpen, setMobileOpen]);

  // A route change always closes the drawer.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname, setMobileOpen]);

  return (
    <>
      <nav
        aria-label="Primary"
        className={clsx(
          "hidden h-dvh shrink-0 flex-col border-r bg-[var(--bg-card)] transition-[width] duration-200 [transition-timing-function:var(--motion-ease)] md:flex",
          collapsed ? "w-16" : "w-56",
        )}
      >
        <div className={clsx("flex h-14 items-center px-3", collapsed ? "justify-center" : "justify-between")}>
          {!collapsed && (
            <Link href="/app" className="text-sm">
              <Wordmark size={18} />
            </Link>
          )}
          <button
            type="button"
            onClick={toggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={`${collapsed ? "Expand" : "Collapse"} sidebar ( [ )`}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]"
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>
        <SidebarBody collapsed={collapsed} practiceMinutesThisWeek={practiceMinutesThisWeek} isAdmin={isAdmin} pathname={pathname} />
      </nav>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/50 animate-fade-in" aria-hidden onClick={() => setMobileOpen(false)} />
          <nav
            aria-label="Primary"
            className="absolute inset-y-0 left-0 flex w-64 max-w-[85vw] flex-col border-r bg-[var(--bg-card)] animate-drawer-in"
          >
            <div className="flex h-14 items-center justify-between px-3">
              <Link href="/app" className="text-sm">
                <Wordmark size={18} />
              </Link>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                autoFocus
                className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]"
              >
                <X size={16} />
              </button>
            </div>
            <SidebarBody
              collapsed={false}
              practiceMinutesThisWeek={practiceMinutesThisWeek}
              isAdmin={isAdmin}
              pathname={pathname}
              onNavigate={() => setMobileOpen(false)}
            />
          </nav>
        </div>
      )}
    </>
  );
}

