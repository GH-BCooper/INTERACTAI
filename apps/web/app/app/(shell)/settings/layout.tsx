"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const TABS = [
  { href: "/app/settings", label: "Profile" },
  { href: "/app/settings/audio", label: "Audio" },
  { href: "/app/settings/privacy", label: "Privacy" },
  { href: "/app/settings/models", label: "Models" },
  { href: "/app/settings/notifications", label: "Notifications" },
];

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h1 className="text-lg font-medium">Settings</h1>

      <nav aria-label="Settings sections" className="mt-5 flex gap-1 border-b">
        {TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <a
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
                active
                  ? "border-[var(--accent)] font-medium text-[var(--text-primary)]"
                  : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {tab.label}
            </a>
          );
        })}
      </nav>

      <div className="mt-6">{children}</div>
    </div>
  );
}
