import { beforeEach, describe, expect, it } from "vitest";

import { usePracticeStore } from "./practice-store";

describe("usePracticeStore", () => {
  beforeEach(() => {
    usePracticeStore.getState().reset();
  });

  it("accumulates persona caption deltas and shows the full line once done", () => {
    const { appendPersonaCaption } = usePracticeStore.getState();
    appendPersonaCaption("Tell me about ", false);
    expect(usePracticeStore.getState().captionText).toBe("Tell me about ");
    appendPersonaCaption("a recent project.", false);
    expect(usePracticeStore.getState().captionText).toBe("Tell me about a recent project.");
    appendPersonaCaption("", true);
    expect(usePracticeStore.getState().captionText).toBe("Tell me about a recent project.");
    expect(usePracticeStore.getState().captionSpeaker).toBe("persona");
  });

  it("a new persona turn starts its buffer fresh, not appended to the previous turn", () => {
    const { appendPersonaCaption } = usePracticeStore.getState();
    appendPersonaCaption("First reply.", false);
    appendPersonaCaption("", true);
    appendPersonaCaption("Second reply.", false);
    expect(usePracticeStore.getState().captionText).toBe("Second reply.");
  });

  it("user partial transcript overwrites the caption and marks the speaker", () => {
    const { setUserPartialCaption } = usePracticeStore.getState();
    setUserPartialCaption("I think that");
    expect(usePracticeStore.getState().captionText).toBe("I think that");
    expect(usePracticeStore.getState().captionSpeaker).toBe("user");
  });

  it("setEnded moves client_state and connection to their terminal values", () => {
    usePracticeStore.getState().setEnded("user_hangup", true);
    const state = usePracticeStore.getState();
    expect(state.ended).toBe(true);
    expect(state.clientState).toBe("ended");
    expect(state.connection).toBe("ended");
    expect(state.reportPending).toBe(true);
  });

  it("reset returns every field to its initial value", () => {
    usePracticeStore.getState().setMuted(true);
    usePracticeStore.getState().setElapsedMs(5000);
    usePracticeStore.getState().reset();
    const state = usePracticeStore.getState();
    expect(state.muted).toBe(false);
    expect(state.elapsedMs).toBe(0);
  });
});
