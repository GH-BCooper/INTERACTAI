/**
 * Hand-maintained (not generated) — pair with the `WsMessage` union in ./ws-types.ts.
 *
 * Put `assertNever(msg)` in the `default` case of a `switch (msg.type)`. If a message type is
 * ever added to the schema and this switch isn't updated, TypeScript raises a compile error
 * here instead of silently swallowing the new message at runtime.
 *
 * @example
 * switch (msg.type) {
 *   case "partial_transcript": ...; break;
 *   case "turn_finalized":     ...; break;
 *   // ...every other WsMessage variant...
 *   default: assertNever(msg);
 * }
 */
export function assertNever(value: never): never {
  throw new Error(`unhandled WsMessage variant: ${JSON.stringify(value)}`);
}
