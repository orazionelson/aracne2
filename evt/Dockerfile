# ── Stage 1: build EVT 2 from source ─────────────────────────────────────────
# node-sass@4.x requires Python and native build tools; Node 14 is the last
# version fully supported by this AngularJS-era dependency chain.
FROM node:14-alpine AS builder

RUN apk add --no-cache git python3 make g++ && \
    ln -sf python3 /usr/bin/python

WORKDIR /build

# Clone EVT 2 (latest stable branch)
RUN git clone --depth 1 https://github.com/evt-project/evt-viewer.git .

# --ignore-scripts prevents phantomjs-prebuilt from downloading its binary
# at install time (it is a test-only dependency, not needed for the build).
# npm rebuild node-sass then compiles only the native bindings we do need.
RUN npm install --legacy-peer-deps --ignore-scripts && \
    npm rebuild node-sass

# Build the distribution
RUN npm run build

# ── Stage 2: serve with nginx ─────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Remove the default nginx server block
RUN rm -f /etc/nginx/conf.d/default.conf.default

EXPOSE 80
