"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { bootstrapAuth } from "@/lib/api/client";

/** A returning signed-in visitor landing on `/` (tab reopened, bookmark, etc.) should go
 * straight to `/app` rather than see the sign-in buttons again. Silent and cheap: one
 * `/auth/refresh` call against the httpOnly cookie, no visible loading state — if it fails,
 * the sign-in page underneath is already correct. */
export function RedirectIfAuthenticated() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    void bootstrapAuth().then((ok) => {
      if (!cancelled && ok) router.replace("/app");
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return null;
}
