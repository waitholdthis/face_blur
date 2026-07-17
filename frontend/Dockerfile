ARG BASE_IMAGE=node:22-alpine

# --- deps + build ---
FROM ${BASE_IMAGE} AS builder
WORKDIR /app

# Optional PEM bundle (build arg) for networks that intercept TLS with a
# private CA; appended to Node's trust store for the npm install.
ARG EXTRA_CA_BUNDLE=""

COPY package.json package-lock.json* ./
RUN if [ -n "$EXTRA_CA_BUNDLE" ]; then \
        printf '%s\n' "$EXTRA_CA_BUNDLE" > /tmp/extra-ca.crt; \
        export NODE_EXTRA_CA_CERTS=/tmp/extra-ca.crt; \
    fi; \
    npm ci
COPY . .
# API base is baked in at build time for the browser bundle; override as needed.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runtime ---
FROM ${BASE_IMAGE} AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.mjs ./next.config.mjs
EXPOSE 3000
CMD ["npm", "run", "start"]
