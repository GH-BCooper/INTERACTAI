"use client";

import { clsx } from "clsx";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const EXIT_MS = 150; // --motion-fast

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** docs/ui-audit-2026-09.md §1.7 — the one modal primitive. Every modal in the app goes through
 * this so they all get the same behaviour:
 *
 *   - focus moves into the panel on open (an `autoFocus` child wins, else the first focusable),
 *     Tab/Shift+Tab are trapped inside it, and focus returns to the opener on close;
 *   - the page behind does not scroll while it is open;
 *   - Escape and a backdrop click call `onClose` (both can be turned off for a flow that must be
 *     finished, e.g. consent);
 *   - a 150 ms fade + scale on enter and exit using `--motion-ease` (reduced motion is already
 *     neutralised globally in globals.css).
 *
 * It stays mounted for the exit animation, so callers pass `open` rather than unmounting it. */
export function Dialog({
  open,
  onClose,
  labelledBy,
  describedBy,
  role = "dialog",
  dismissible = true,
  className,
  position = "center",
  children,
}: {
  open: boolean;
  onClose: () => void;
  labelledBy?: string;
  describedBy?: string;
  role?: "dialog" | "alertdialog";
  dismissible?: boolean;
  className?: string;
  position?: "center" | "top";
  children: ReactNode;
}) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<Element | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Mount → next frame → visible (so the enter transition actually runs); close → hide → unmount.
  useEffect(() => {
    if (open) {
      openerRef.current = document.activeElement;
      setMounted(true);
      const frame = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(frame);
    }
    setVisible(false);
    const timer = setTimeout(() => setMounted(false), EXIT_MS);
    return () => clearTimeout(timer);
  }, [open]);

  // Scroll lock + initial focus + focus restore, for as long as it is open.
  useEffect(() => {
    if (!open || !mounted) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const panel = panelRef.current;
    const preferred = panel?.querySelector<HTMLElement>("[autofocus], [data-autofocus]");
    const first = panel?.querySelector<HTMLElement>(FOCUSABLE);
    (preferred ?? first ?? panel)?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      const opener = openerRef.current;
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus();
    };
  }, [open, mounted]);

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      if (dismissible) {
        e.stopPropagation();
        onCloseRef.current();
      }
      return;
    }
    if (e.key !== "Tab" || !panelRef.current) return;
    // Attribute-based, not `offsetParent`: that is null for anything under a fixed-position
    // ancestor in some engines, which would silently shrink the trap to nothing.
    const items = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => !el.closest("[hidden], [aria-hidden='true'], [inert]"),
    );
    if (items.length === 0) {
      e.preventDefault();
      return;
    }
    const firstItem = items[0];
    const lastItem = items[items.length - 1];
    if (e.shiftKey && document.activeElement === firstItem) {
      e.preventDefault();
      lastItem?.focus();
    } else if (!e.shiftKey && document.activeElement === lastItem) {
      e.preventDefault();
      firstItem?.focus();
    }
  }

  if (!mounted || typeof document === "undefined") return null;

  return createPortal(
    <div
      className={clsx(
        "fixed inset-0 z-50 flex justify-center p-4 transition-opacity duration-150 [transition-timing-function:var(--motion-ease)]",
        position === "top" ? "items-start pt-[12vh]" : "items-center",
        visible ? "opacity-100" : "opacity-0",
      )}
      onKeyDown={onKeyDown}
    >
      <div
        aria-hidden
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
        onClick={dismissible ? () => onCloseRef.current() : undefined}
      />
      <div
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        tabIndex={-1}
        className={clsx(
          "relative w-full rounded-lg border bg-[var(--bg-card)] outline-none transition-transform duration-150 [transition-timing-function:var(--motion-ease)]",
          visible ? "scale-100" : "scale-[0.97]",
          className ?? "max-w-sm p-5",
        )}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
