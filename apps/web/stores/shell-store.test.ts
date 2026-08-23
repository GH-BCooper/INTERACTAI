/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it } from "vitest";

import { useShellStore } from "./shell-store";

const CAPTIONS_KEY = "interactai-captions-enabled";

describe("shell-store: seedCaptionsDefault", () => {
  beforeEach(() => {
    localStorage.clear();
    useShellStore.setState({ captionsEnabled: true });
  });

  it("applies the server default when no local choice has ever been made", () => {
    useShellStore.getState().seedCaptionsDefault(false);
    expect(useShellStore.getState().captionsEnabled).toBe(false);
    expect(localStorage.getItem(CAPTIONS_KEY)).toBe("false");
  });

  it("does not override an explicit local choice with the server default", () => {
    useShellStore.getState().setCaptionsEnabled(true);
    useShellStore.getState().seedCaptionsDefault(false);
    expect(useShellStore.getState().captionsEnabled).toBe(true);
  });

  it("does not override a local choice even when it happens to match the server default", () => {
    useShellStore.getState().setCaptionsEnabled(false);
    useShellStore.getState().seedCaptionsDefault(true);
    expect(useShellStore.getState().captionsEnabled).toBe(false);
    expect(localStorage.getItem(CAPTIONS_KEY)).toBe("false");
  });
});
