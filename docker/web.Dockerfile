# ARGUS web image.

FROM node:20-alpine AS deps

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund


FROM node:20-alpine AS builder

# No API URL is needed at build time. The client calls its own origin and
# next.config.mjs proxies /api to the backend from a runtime variable, so the
# backend can move without rebuilding the image.
ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./
RUN npm run build


FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

RUN addgroup -g 10001 -S argus && adduser -S argus -u 10001 -G argus

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/scripts ./scripts

USER argus
EXPOSE 3000

CMD ["node", "scripts/next.mjs", "start", "-p", "3000"]
