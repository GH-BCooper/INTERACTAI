/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it } from "vitest";

import {
  getSavedInputDeviceId,
  getSavedOutputDeviceId,
  setSavedInputDeviceId,
  setSavedOutputDeviceId,
} from "./device-prefs";

describe("device-prefs", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when nothing has been saved", () => {
    expect(getSavedInputDeviceId()).toBeNull();
    expect(getSavedOutputDeviceId()).toBeNull();
  });

  it("round-trips a saved input device id", () => {
    setSavedInputDeviceId("mic-123");
    expect(getSavedInputDeviceId()).toBe("mic-123");
  });

  it("round-trips a saved output device id independently of the input one", () => {
    setSavedInputDeviceId("mic-123");
    setSavedOutputDeviceId("speaker-456");
    expect(getSavedInputDeviceId()).toBe("mic-123");
    expect(getSavedOutputDeviceId()).toBe("speaker-456");
  });

  it("overwrites a previously saved value", () => {
    setSavedInputDeviceId("mic-123");
    setSavedInputDeviceId("mic-789");
    expect(getSavedInputDeviceId()).toBe("mic-789");
  });
});
