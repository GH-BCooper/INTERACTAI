/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dialog } from "./dialog";
import { formatRelative } from "./local-date";
import { Segmented } from "./segmented";

describe("Dialog", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0));
    vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    document.body.style.overflow = "";
  });

  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          opener
        </button>
        <Dialog open={open} onClose={() => setOpen(false)} labelledBy="t">
          <h2 id="t">Title</h2>
          <button type="button">first</button>
          <button type="button" data-autofocus>
            preferred
          </button>
          <button type="button">last</button>
        </Dialog>
      </>
    );
  }

  it("focuses the preferred element, locks scroll, traps Tab, and restores focus on Escape", () => {
    render(<Harness />);
    const opener = screen.getByText("opener");
    opener.focus();
    fireEvent.click(opener);
    act(() => {
      vi.runOnlyPendingTimers();
    });

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByText("preferred"));
    expect(document.body.style.overflow).toBe("hidden");

    // Tab from the last focusable wraps to the first.
    screen.getByText("last").focus();
    fireEvent.keyDown(screen.getByText("last"), { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("first"));
    // Shift+Tab from the first wraps to the last.
    fireEvent.keyDown(screen.getByText("first"), { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText("last"));

    fireEvent.keyDown(screen.getByText("last"), { key: "Escape" });
    act(() => {
      vi.advanceTimersByTime(200); // exit animation
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
    expect(document.activeElement).toBe(opener);
  });

  it("does not close on Escape when not dismissible", () => {
    const onClose = vi.fn();
    render(
      <Dialog open onClose={onClose} dismissible={false}>
        <button type="button">only</button>
      </Dialog>,
    );
    act(() => {
      vi.runOnlyPendingTimers();
    });
    fireEvent.keyDown(screen.getByText("only"), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("Segmented", () => {
  it("is a radio group whose arrow keys move and select", () => {
    function Harness() {
      const [value, setValue] = useState<"a" | "b" | "c">("a");
      return (
        <Segmented
          label="Pick"
          value={value}
          onChange={setValue}
          options={[
            { value: "a", label: "A" },
            { value: "b", label: "B" },
            { value: "c", label: "C" },
          ]}
        />
      );
    }
    render(<Harness />);
    const a = screen.getByRole("radio", { name: "A" });
    expect(a).toHaveAttribute("aria-checked", "true");
    expect(a).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: "B" })).toHaveAttribute("tabindex", "-1");

    fireEvent.keyDown(a, { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "B" })).toHaveAttribute("aria-checked", "true");
    // Wraps around from the first to the last.
    fireEvent.keyDown(screen.getByRole("radio", { name: "B" }), { key: "ArrowLeft" });
    fireEvent.keyDown(screen.getByRole("radio", { name: "A" }), { key: "ArrowLeft" });
    expect(screen.getByRole("radio", { name: "C" })).toHaveAttribute("aria-checked", "true");
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-09-30T12:00:00Z");
  it("says 'just now' under a minute", () => {
    expect(formatRelative(new Date("2026-09-30T11:59:30Z"), now)).toBe("just now");
  });
  it("uses the largest whole unit", () => {
    expect(formatRelative(new Date("2026-09-28T12:00:00Z"), now)).toMatch(/2 days ago/);
    expect(formatRelative(new Date("2026-09-30T09:00:00Z"), now)).toMatch(/3 hours ago/);
  });
});
