# ARGUS web image.

FROM node:20-alpine AS deps

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund


FROM node:20-alpine AS builder

# Next.js inlines NEXT_PUBLIC_* into the client bundle at build time, so this
# has to be correct when the image is built, not when it runs. The default is
# the deployed API; docker-compose overrides it for local use.
ARG NEXT_PUBLIC_API_BASE_URL=https://argus-api.onrender.com
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1

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
