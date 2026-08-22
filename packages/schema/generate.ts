// Regenerate TypeScript types from ws-messages.schema.json. Run via `pnpm run generate:ts`
// (wired into `make schema`). Output: apps/web/lib/ws-types.ts.
//
// Deterministic: two consecutive runs produce byte-identical output.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile, type JSONSchema } from "json-schema-to-typescript";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const SCHEMA_FILE = resolve(REPO_ROOT, "packages/schema/ws-messages.schema.json");
const OUTPUT_FILE = resolve(REPO_ROOT, "apps/web/lib/ws-types.ts");

const HEADER = `/* eslint-disable */
/**
 * GENERATED — DO NOT EDIT. Run \`make schema\`.
 *
 * Source: packages/schema/ws-messages.schema.json
 * Generator: packages/schema/generate.ts -> json-schema-to-typescript
 */
`;

// Message defs, in schema order — becomes the discriminated WsMessage union.
const MESSAGE_TYPES = [
  "hello",
  "resume",
  "mute",
  "end_session",
  "ping",
  "ready",
  "state_change",
  "partial_transcript",
  "turn_finalized",
  "persona_text",
  "audio_chunk_meta",
  "interrupted",
  "degraded",
  "latency_report",
  "session_closed",
  "error",
  "pong",
] as const;

// `error`'s generated name is overridden (via the schema's own `title: "WsError"`) so it
// doesn't shadow the global `Error` type.
const NAME_OVERRIDES: Partial<Record<(typeof MESSAGE_TYPES)[number], string>> = {
  error: "WsError",
};

function pascalCase(snake: string): string {
  const override = NAME_OVERRIDES[snake as (typeof MESSAGE_TYPES)[number]];
  if (override) return override;
  return snake
    .split("_")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join("");
}

async function main() {
  const raw = readFileSync(SCHEMA_FILE, "utf-8");
  const schema = JSON.parse(raw) as JSONSchema & { $defs: Record<string, JSONSchema> };

  const compileOptions = {
    bannerComment: "",
    additionalProperties: false as const,
    unreachableDefinitions: true,
    style: { semi: true, singleQuote: false },
  };

  // Compile $defs in isolation (no root oneOf/title) so every definition is emitted exactly
  // once, deduped by the parser's internal cache, with no spurious root union pulling in the
  // schema's own `title` as a type name. The root itself has no shape of its own — drop the
  // empty `WsDefs` wrapper interface that compiling an untyped root otherwise emits.
  const rawTs = await compile({ $defs: schema.$defs }, "WsDefs", compileOptions);
  const ts = rawTs.replace(/export interface WsDefs \{\s*\[k: string\]: unknown;\s*\}\s*/, "");

  const unionName = "WsMessage";
  const unionMembers = MESSAGE_TYPES.map(pascalCase).join(" | ");

  const output = [
    HEADER,
    ts.trim(),
    `export type ${unionName} = ${unionMembers};`,
  ].join("\n\n") + "\n";

  mkdirSync(dirname(OUTPUT_FILE), { recursive: true });
  writeFileSync(OUTPUT_FILE, output, "utf-8");
  console.log(`wrote ${OUTPUT_FILE}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
