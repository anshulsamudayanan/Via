# syntax=docker/dockerfile:1
# VIA web image: Next.js standalone server.
# Build context: repository root.
# Optional build secret `build_ca`: extra CA bundle for TLS-intercepting proxies
# (set VIA_BUILD_CA_CERT for Compose). Never copied into an image layer.

FROM node:22.21.1-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    corepack enable && corepack prepare pnpm@10.28.0 --activate
WORKDIR /repo

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/ui/package.json packages/ui/
COPY packages/api-client/package.json packages/api-client/
COPY packages/types/package.json packages/types/
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    pnpm install --frozen-lockfile --filter "@via/web..."

FROM deps AS build
COPY tsconfig.base.json ./
COPY packages ./packages
COPY apps/web ./apps/web
# Where the Next.js server proxies /api/*; baked into the standalone build's routes.
ARG VIA_API_INTERNAL_URL=http://api:8000
ENV VIA_API_INTERNAL_URL=${VIA_API_INTERNAL_URL}
# The web proxy must accept request bodies at least this large (PCB uploads).
ARG VIA_MAX_UPLOAD_BYTES=52428800
ENV VIA_MAX_UPLOAD_BYTES=${VIA_MAX_UPLOAD_BYTES}
# Array display font (ITF Free Font License: self-hosted, never committed). Best effort: without
# network the site falls back to the system display font.
COPY scripts/fetch-fonts.mjs scripts/
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    NODE_USE_ENV_PROXY=1 node scripts/fetch-fonts.mjs
RUN pnpm --filter @via/web build

FROM node:22.21.1-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S via && adduser -S via -G via
WORKDIR /app
COPY --from=build --chown=via:via /repo/apps/web/.next/standalone ./
COPY --from=build --chown=via:via /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=via:via /repo/apps/web/public ./apps/web/public
USER via
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:3000/"]
CMD ["node", "apps/web/server.js"]
