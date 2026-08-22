/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAudioCapture } from "./use-audio-capture";

const { createMicCaptureMock } = vi.hoisted(() => ({ createMicCaptureMock: vi.fn() }));

vi.mock("@/lib/audio/capture", () => ({
  createMicCapture: createMicCaptureMock,
}));

function renderUseAudioCapture() {
  return renderHook(() => {
    const ref = useRef<HTMLDivElement>(null);
    return useAudioCapture({ onFrame: vi.fn(), meterElementRef: ref });
  });
}

describe("useAudioCapture", () => {
  beforeEach(() => {
    createMicCaptureMock.mockReset();
    Object.defineProperty(globalThis.navigator, "mediaDevices", {
      configurable: true,
      value: { addEventListener: vi.fn(), removeEventListener: vi.fn() },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("maps NotAllowedError to denied", async () => {
    createMicCaptureMock.mockRejectedValue(
      Object.assign(new DOMException("denied", "NotAllowedError")),
    );
    const { result } = renderUseAudioCapture();

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.permission).toBe("denied");
  });

  it("maps NotFoundError to no_device", async () => {
    createMicCaptureMock.mockRejectedValue(new DOMException("no device", "NotFoundError"));
    const { result } = renderUseAudioCapture();

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.permission).toBe("no_device");
  });

  it("transitions to granted on success and revoked when the track ends", async () => {
    let capturedOnTrackEnded: (() => void) | undefined;
    createMicCaptureMock.mockImplementation(async (handlers: { onTrackEnded?: () => void }) => {
      capturedOnTrackEnded = handlers.onTrackEnded;
      return { setMuted: vi.fn(), stop: vi.fn() };
    });
    const { result } = renderUseAudioCapture();

    await act(async () => {
      await result.current.start();
    });
    expect(result.current.permission).toBe("granted");

    act(() => {
      capturedOnTrackEnded?.();
    });
    await waitFor(() => expect(result.current.permission).toBe("revoked"));
  });

  it("a start() called and then immediately stopped never leaves capture running", async () => {
    const stopFn = vi.fn().mockResolvedValue(undefined);
    let resolveCreate: (value: { setMuted: () => void; stop: () => Promise<void> }) => void;
    createMicCaptureMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const { result } = renderUseAudioCapture();

    let startPromise!: Promise<void>;
    act(() => {
      startPromise = result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    resolveCreate!({ setMuted: vi.fn(), stop: stopFn });
    await act(async () => {
      await startPromise;
    });

    expect(stopFn).toHaveBeenCalled();
  });
});
