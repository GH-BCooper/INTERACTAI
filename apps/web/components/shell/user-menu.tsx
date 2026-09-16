"use client";

import { LogOut, Moon, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api/client";
import type { MeOut } from "@/lib/api/types";
import { useAuthStore } from "@/stores/auth-store";
import { useThemeStore } from "@/stores/theme-store";

export function UserMenu({ me }: { me: MeOut }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const clearAuth = useAuthStore((s) => s.clear);
  const toggleTheme = useThemeStore((s) => s.toggle);
  const preference = useThemeStore((s) => s.preference);

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  async function signOut() {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, { method: "POST", credentials: "include" });
    } finally {
      clearAuth();
      router.replace("/signin");
    }
  }

  const initial = (me.user.name ?? me.user.email).charAt(0).toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--bg-raised)] text-xs font-medium"
      >
        {initial}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-10 z-40 w-52 rounded-md border bg-[var(--bg-card)] p-1 text-sm shadow-none"
        >
          <div className="px-2 py-1.5 text-xs text-[var(--text-tertiary)]">
            {me.user.name ?? me.user.email}
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => toggleTheme()}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--bg-raised)]"
          >
            {preference === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            Toggle theme
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[var(--bg-raised)]"
          >
            <LogOut size={14} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
