"use client";

import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/client";

import { Button, ButtonLink } from "./button";

/** CLAUDE.md §6: every error the user can meet has a code, a message and a recovery path —
 * never a stack trace. Used by every `error.tsx` boundary. An `ApiError` carries all three from
 * the server; anything else is an unexpected client failure and gets a generic, honest message
 * with the Next.js digest as its trace id. */
export function ErrorState({
  error,
  reset,
  homeHref = "/app",
  homeLabel = "Back to dashboard",
  fullPage = false,
}: {
  error: Error & { digest?: string };
  reset?: () => void;
  homeHref?: string;
  homeLabel?: string;
  fullPage?: boolean;
}) {
  const api = error instanceof ApiError ? error : null;
  const code = api?.code ?? "ORCHESTRATION_CLIENT_ERROR";
  const message = api?.message ?? "Something went wrong while showing this page.";
  const recovery = api?.recovery ?? "Try again. If it keeps happening, go back and reopen the page.";
  const trace = api?.traceId || error.digest;

  return (
    <Frame fullPage={fullPage}>
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-raised)] text-[var(--status-bad)]">
        <AlertTriangle size={18} aria-hidden />
      </div>
      <h1 className="text-md font-medium">{message}</h1>
      <p className="max-w-sm text-sm text-[var(--text-secondary)]">{recovery}</p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {reset && (
          <Button variant="primary" size="sm" onClick={reset}>
            Try again
          </Button>
        )}
        <ButtonLink href={homeHref} variant="secondary" size="sm">
          {homeLabel}
        </ButtonLink>
      </div>
      <p className="mt-2 font-mono text-xs text-[var(--text-tertiary)]">
        {code}
        {trace ? ` · ${trace}` : ""}
      </p>
    </Frame>
  );
}

function Frame({ fullPage, children }: { fullPage: boolean; children: ReactNode }) {
  return (
    <div
      role="alert"
      className={
        fullPage
          ? "flex min-h-dvh flex-col items-center justify-center gap-3 bg-[var(--bg-page)] px-6 text-center"
          : "mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center"
      }
    >
      {children}
    </div>
  );
}
