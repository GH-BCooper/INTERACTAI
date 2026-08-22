import { describe, expect, it } from "vitest";

import { detectBrowser } from "./browser-detect";

const CHROME_WINDOWS =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const FIREFOX_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0";
const SAFARI_MAC =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15";
const EDGE_WINDOWS =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0";

describe("detectBrowser", () => {
  it("identifies Chrome despite its UA also containing 'Safari'", () => {
    expect(detectBrowser(CHROME_WINDOWS)).toBe("chrome");
  });

  it("identifies Firefox", () => {
    expect(detectBrowser(FIREFOX_WINDOWS)).toBe("firefox");
  });

  it("identifies real Safari (no Chrome/Chromium token present)", () => {
    expect(detectBrowser(SAFARI_MAC)).toBe("safari");
  });

  it("treats Chromium-based Edge as chrome (same permission UI)", () => {
    expect(detectBrowser(EDGE_WINDOWS)).toBe("chrome");
  });

  it("falls back to other for anything unrecognized", () => {
    expect(detectBrowser("SomeBot/1.0")).toBe("other");
  });
});
