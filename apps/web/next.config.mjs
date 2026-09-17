/* global process */
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase 6 TASK 6.4a: self-contained server bundle, enabled only by apps/web/Dockerfile. Off by
  // default: standalone tracing needs symlink rights a normal Windows dev shell does not have.
  output: process.env.NEXT_OUTPUT_STANDALONE === "1" ? "standalone" : undefined,
};

export default nextConfig;
