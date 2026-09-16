import type { Metadata } from "next";
import { JetBrains_Mono, Inter } from "next/font/google";
import type { ReactNode } from "react";

import { Providers } from "./providers";
import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-sans",
  // "optional": no late font swap re-laying out text after first paint (Lighthouse LCP/CLS, TASK 6.6).
  display: "optional",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  // "optional": no late font swap re-laying out text after first paint (Lighthouse LCP/CLS, TASK 6.6).
  display: "optional",
});

export const metadata: Metadata = {
  title: "InteractAI",
  description: "Speak. Be answered convincingly and fast. Be scored defensibly.",
};

// Runs before hydration so the very first paint already has the right theme — without this a
// dark-preferring user with a saved "light" choice sees one dark frame on every navigation.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("interactai-theme");
    if (stored === "light" || stored === "dark") {
      document.documentElement.setAttribute("data-theme", stored);
    }
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Static string above, no user input — safe. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
