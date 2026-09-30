import Link from "next/link";
import type { ReactNode } from "react";

import { Wordmark } from "@/components/ui/logo";

/** Shared frame for the short public policy pages linked from the footer and sign-in. */
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <main className="min-h-dvh">
      <header className="mx-auto flex max-w-2xl items-center justify-between px-4 py-5 sm:px-6">
        <Link href="/" aria-label="InteractAI home">
          <Wordmark />
        </Link>
        <Link href="/" className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
          Home
        </Link>
      </header>
      <article className="mx-auto max-w-2xl px-4 pb-20 pt-6 sm:px-6">
        <h1 className="text-lg font-medium">{title}</h1>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">Last updated {updated}</p>
        <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-[var(--text-secondary)] [&_h2]:text-md [&_h2]:font-medium [&_h2]:text-[var(--text-primary)] [&_ul]:list-disc [&_ul]:pl-5">
          {children}
        </div>
      </article>
    </main>
  );
}
