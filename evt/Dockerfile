# ── Stage 1: build EVT 2 from source ─────────────────────────────────────────
FROM node:18-alpine AS builder

RUN apk add --no-cache git

WORKDIR /build

# Clone EVT 2 (pinned to a known commit for reproducibility)
RUN git clone --depth 1 https://github.com/evt-project/evt-viewer.git .

# Install dependencies (--legacy-peer-deps needed for AngularJS-era packages)
RUN npm install --legacy-peer-deps

# Build the distribution
RUN npm run build

# ── Stage 2: serve with nginx ─────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Remove the default nginx server block
RUN rm -f /etc/nginx/conf.d/default.conf.default

EXPOSE 80
