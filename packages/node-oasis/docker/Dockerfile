# ============================================================
# Stage 1: Builder
# - Install deps, run build.py to download Node.js distributions
# Build context: workspace root (docker build -f packages/node-oasis/docker/Dockerfile .)
# ============================================================
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:python3.14-alpine AS builder

# uv best practices
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1

WORKDIR /app

# Intermediate layer: install dependencies first (Docker cache friendly)
# Workspace root pyproject.toml + uv.lock + all member pyproject.toml needed for uv sync
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=packages/node-oasis/pyproject.toml,target=packages/node-oasis/pyproject.toml \
    --mount=type=bind,source=packages/uv-oasis/pyproject.toml,target=packages/uv-oasis/pyproject.toml \
    uv sync --locked --no-install-project --package node-oasis

# Copy only the necessary python source code
COPY packages/node-oasis/build.py /app/
COPY packages/node-oasis/config.toml /app/
COPY packages/node-oasis/node_oasis /app/node_oasis

# Run build script: download Node.js distributions + generate indexes
# UPSTREAM_FINGERPRINT invalidates this layer's cache whenever upstream versions change
ARG UPSTREAM_FINGERPRINT=""
RUN --mount=type=secret,id=GITHUB_TOKEN,required=false \
    GITHUB_TOKEN=$(cat /run/secrets/GITHUB_TOKEN 2>/dev/null || echo "") \
    UPSTREAM_FINGERPRINT="${UPSTREAM_FINGERPRINT}" \
    uv run python build.py --latest-lts --output /app/dist

# ============================================================
# Stage 2: Runtime
# - Pure nginx static file server, no Python/uv needed
# ============================================================
FROM nginxinc/nginx-unprivileged:alpine-slim

# Switch to root to perform OS upgrades and set permissions
USER root
RUN apk upgrade --no-cache

LABEL org.opencontainers.image.title="node-oasis"
LABEL org.opencontainers.image.description="Offline Node.js mirror for NVM/fnm in air-gapped environments"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/pTaunium/oasis"

# nginx-unprivileged expects templates in /etc/nginx/templates
COPY --chown=nginx:nginx packages/node-oasis/docker/nginx.conf /etc/nginx/templates/default.conf.template
COPY --chown=nginx:nginx packages/node-oasis/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# We must ensure nginx user has write access to the html directory
# because entrypoint.sh generates setup scripts from templates at runtime
RUN chown -R nginx:nginx /usr/share/nginx/html

# Copy documentation and licenses
COPY --chown=nginx:nginx LICENSE /usr/share/nginx/html/LICENSE
COPY --chown=nginx:nginx packages/node-oasis/README.md /usr/share/nginx/html/README.md

# Copy build artifacts from builder
COPY --chown=nginx:nginx --from=builder /app/dist/dist/ /usr/share/nginx/html/dist/
COPY --chown=nginx:nginx --from=builder /app/dist/tools/ /usr/share/nginx/html/tools/

# Switch back to the unprivileged user before running
USER nginx

EXPOSE 8080

# Upstream versions snapshot (Node.js LTS + nvm + fnm), read by CI to skip unchanged builds.
# Kept last so a changed value does not invalidate earlier layers.
ARG UPSTREAM_FINGERPRINT=""
LABEL io.github.ptaunium.node-oasis.upstream-fingerprint="${UPSTREAM_FINGERPRINT}"

ENTRYPOINT ["/entrypoint.sh"]
