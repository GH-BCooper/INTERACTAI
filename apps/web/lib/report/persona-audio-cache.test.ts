import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PersonaAudioCache } from "./persona-audio-cache";

vi.mock("@/lib/api/resources", () => ({
  sessions: {
    mintReplayToken: vi.fn().mockResolvedValue({ token: "tok-1", expires_in: 3600 }),
  },
}));

describe("PersonaAudioCache", () => {
  let createObjectURLSpy: ReturnType<typeof vi.fn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    createObjectURLSpy = vi.fn(() => "blob:fake-url");
    revokeObjectURLSpy = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: createObjectURLSpy, revokeObjectURL: revokeObjectURLSpy });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["fake audio"]) }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("fetches and caches audio for a turn, reusing it on a second call", async () => {
    const cache = new PersonaAudioCache("session-1", "http://fake-realtime");
    const url1 = await cache.getAudioUrl("turn-1", "Hello.", "voice-a");
    const url2 = await cache.getAudioUrl("turn-1", "Hello.", "voice-a");

    expect(url1).toBe("blob:fake-url");
    expect(url2).toBe("blob:fake-url");
    expect(globalThis.fetch).toHaveBeenCalledTimes(1); // second call served from cache
  });

  it("returns null (never throws) when the synthesize endpoint fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    const cache = new PersonaAudioCache("session-1", "http://fake-realtime");
    await expect(cache.getAudioUrl("turn-1", "Hello.", "voice-a")).resolves.toBeNull();
  });

  it("returns null when the network request itself throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const cache = new PersonaAudioCache("session-1", "http://fake-realtime");
    await expect(cache.getAudioUrl("turn-1", "Hello.", "voice-a")).resolves.toBeNull();
  });

  it("dispose() revokes every cached object URL", async () => {
    const cache = new PersonaAudioCache("session-1", "http://fake-realtime");
    await cache.getAudioUrl("turn-1", "Hello.", "voice-a");
    cache.dispose();
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:fake-url");
  });
});
