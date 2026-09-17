# Phase 6 TASK 6.4a — web, for the self-host path (the hosted instance runs on Vercel).
# Build from the repo root: docker build -f apps/web/Dockerfile .
FROM node:22-bookworm-slim AS builder
RUN corepack enable
WORKDIR /repo
# Dependency manifests first, source last — a code change does not re-install node_modules.
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/schema/package.json packages/schema/package.json
RUN pnpm install --frozen-lockfile --filter @interactai/web...
COPY packages/schema packages/schema
COPY apps/web apps/web
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_REALTIME_HTTP_URL=http://localhost:8080
ARG NEXT_PUBLIC_SELF_HOST=false
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_REALTIME_HTTP_URL=$NEXT_PUBLIC_REALTIME_HTTP_URL \
    NEXT_PUBLIC_SELF_HOST=$NEXT_PUBLIC_SELF_HOST \
    NEXT_OUTPUT_STANDALONE=1 \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @interactai/web run build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
COPY --from=builder --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=node:node /repo/apps/web/public ./apps/web/public
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/demo').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "apps/web/server.js"]
