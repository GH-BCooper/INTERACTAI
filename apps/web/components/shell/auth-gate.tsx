"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { bootstrapAuth } from "@/lib/api/client";
import { useAuthStore } from "@/stores/auth-store";

import { FullPageLoading } from "./full-page-loading";

/** Every route under /app is authenticated. `status` starts "unknown" on a hard reload (the
 * access token lives in memory only) — this silently exchanges the httpOnly refresh cookie for
 * a fresh one before rendering anything, and sends an anonymous visitor back to sign in rather
 * than flashing authenticated chrome around no data. */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const router = useRouter();

  useEffect(() => {
    if (status !== "unknown") return;
    let cancelled = false;
    void bootstrapAuth().then((ok) => {
      if (cancelled) return;
      if (!ok) router.replace("/signin");
    });
    return () => {
      cancelled = true;
    };
  }, [status, router]);

  if (status !== "authenticated") return <FullPageLoading />;
  return <>{children}</>;
}
