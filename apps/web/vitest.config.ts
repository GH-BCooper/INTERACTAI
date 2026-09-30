import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  // Same JSX transform Next uses, so component tests don't need `import React`.
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
  },
});
