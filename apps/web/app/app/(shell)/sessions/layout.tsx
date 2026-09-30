import type { Metadata } from "next";
import type { ReactNode } from "react";

// Re-declares the template: a plain string title here would drop the root's "%s · InteractAI" for child routes.
export const metadata: Metadata = { title: { default: "Session history", template: "%s · InteractAI" } };

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
