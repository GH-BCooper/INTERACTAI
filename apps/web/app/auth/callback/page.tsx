"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageLoading } from "@/components/shell/full-page-loading";
import { useAuthStore } from "@/stores/auth-store";

/** docs/decisions/0013: services/api/app/routers/auth.py's OAuth callback redirects the
 * browser here with `#token=...&expires_in=...` in the URL *fragment* — never sent to any
 * server, including this one, which is exactly why the token has to be read out of
 * `window.location.hash` client-side rather than as a server-rendered prop. */
export default function AuthCallbackPage() {
  const router = useRouter();
  const setToken = useAuthStore((s) => s.setToken);
  const [error, setError] = useState(false);

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const token = params.get("token");
    const expiresIn = Number(params.get("expires_in"));

    if (!token || !Number.isFinite(expiresIn)) {
      setError(true);
      return;
    }
    setToken(token, expiresIn);
    router.replace("/app");
  }, [router, setToken]);

  if (error) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-sm font-medium">Sign-in didn&apos;t complete.</p>
        <a href="/signin" className="text-sm text-[var(--accent)] hover:text-[var(--accent-hover)]">
          Back to sign in
        </a>
      </main>
    );
  }

  return <FullPageLoading />;
}
