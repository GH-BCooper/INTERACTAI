import type { Metadata } from "next";
import type { ReactNode } from "react";

import { SettingsTabs } from "@/components/settings/settings-tabs";

// Re-declares the template: a plain string title here would drop the root's "%s · InteractAI" for child routes.
export const metadata: Metadata = { title: { default: "Settings", template: "%s · InteractAI" } };

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
      <h1 className="text-lg font-medium">Settings</h1>
      <SettingsTabs />
      <div className="mt-6 animate-fade-in">{children}</div>
    </div>
  );
}
