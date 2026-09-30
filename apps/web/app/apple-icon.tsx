import { ImageResponse } from "next/og";

import { BRAND } from "./brand-image-palette";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: BRAND.bgPage }}>
        <svg width="132" height="132" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke={BRAND.accent} strokeWidth="2" />
          <path d="M6.5 12h1.5l1.5-3.5 2 7 2-9 2 7.5 1.5-2h1" stroke={BRAND.textPrimary} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    ),
    size,
  );
}
