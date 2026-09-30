import { ImageResponse } from "next/og";

import { BRAND } from "./brand-image-palette";

export const alt = "InteractAI — rehearse a hard interview out loud, and get a score you can check.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** docs/ui-audit-2026-09.md §1.4 — the share card. Deliberately carries no numbers: a latency
 * or agreement figure out of its context (host class, dataset revision) would mislead, and a
 * placeholder would be a fabricated metric (CLAUDE.md §1.10). The landing page shows the real,
 * sourced numbers. */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: BRAND.bgPage,
          color: BRAND.textPrimary,
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 34 }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke={BRAND.accent} strokeWidth="2" />
            <path d="M6.5 12h1.5l1.5-3.5 2 7 2-9 2 7.5 1.5-2h1" stroke={BRAND.textPrimary} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          InteractAI
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ fontSize: 64, lineHeight: 1.1, maxWidth: 960 }}>
            Rehearse a hard interview out loud, and get a score you can check.
          </div>
          <div style={{ fontSize: 28, color: BRAND.textSecondary, maxWidth: 900 }}>
            An AI interviewer answers by voice. A separate coach scores every answer and links each score to your exact words.
          </div>
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 24, color: BRAND.textSecondary }}>
          <div style={{ display: "flex", border: `2px solid ${BRAND.border}`, borderRadius: 999, padding: "8px 20px" }}>Voice persona</div>
          <div style={{ display: "flex", border: `2px solid ${BRAND.border}`, borderRadius: 999, padding: "8px 20px" }}>Evidence-linked scores</div>
        </div>
      </div>
    ),
    size,
  );
}
