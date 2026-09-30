"use client";

import { clsx } from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

// Notifications is gone until a channel other than the in-app toast exists
// (docs/ui-audit-2026-09.md §11) — a tab of two disabled checkboxes was a dead end.
const TABS = [
  { href: "/app/settings", label: "Profile" },
  { href: "/app/settings/audio", label: "Audio" },
  { href: "/app/settings/privacy", label: "Privacy" },
  { href: "/app/settings/models", label: "Models" },
];

export function SettingsTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Settings sections" className="-mx-4 mt-5 overflow-x-auto border-b px-4 sm:mx-0 sm:px-0">
      <div className="flex min-w-max gap-1">
        {TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={clsx(
                "-mb-px border-b-2 px-3 py-2 text-sm transition-colors duration-150",
                active
                  ? "border-[var(--accent)] font-medium text-[var(--text-primary)]"
                  : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
