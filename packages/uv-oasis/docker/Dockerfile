# ============================================================
# Stage 1: Builder
# - Install deps, run build.py to download Python tarballs + generate JSON
# Build context: workspace root (docker build -f packages/uv-oasis/docker/Dockerfile .)
# ============================================================
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:python3.14-alpine AS builder

# uv best practices
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1

WORKDIR /app

# Intermediate layer: install dependencies first (Docker cache friendly)
# Workspace root pyproject.toml + uv.lock + package pyproject.toml needed for uv sync
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=packages/uv-oasis/pyproject.toml,target=packages/uv-oasis/pyproject.toml \
    uv sync --locked --no-install-project --package uv-oasis

# Copy only the necessary python source code
COPY packages/uv-oasis/build.py /app/
COPY packages/uv-oasis/config.toml /app/
COPY packages/uv-oasis/uv_oasis /app/uv_oasis

# Run build script: download tarballs + generate JSON
RUN uv run python build.py --output /app/dist

# ============================================================
# Stage 2: Runtime
# - Pure nginx static file server, no Python/uv needed
# ============================================================
FROM nginxinc/nginx-unprivileged:alpine-slim

# Switch to root to perform OS upgrades and set permissions
USER root
RUN apk upgrade --no-cache

LABEL org.opencontainers.image.title="uv-oasis"
LABEL org.opencontainers.image.description="Offline Python mirror for uv in air-gapped environments"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/pTaunium/oasis"

# nginx-unprivileged expects templates in /etc/nginx/templates
COPY --chown=nginx:nginx packages/uv-oasis/docker/nginx.conf /etc/nginx/templates/default.conf.template
COPY --chown=nginx:nginx packages/uv-oasis/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# We must ensure nginx user has write access to the html directory
# because entrypoint.sh generates download-metadata.json at runtime
RUN chown -R nginx:nginx /usr/share/nginx/html

# Copy documentation and licenses
COPY --chown=nginx:nginx LICENSE /usr/share/nginx/html/LICENSE
COPY --chown=nginx:nginx packages/uv-oasis/README.md /usr/share/nginx/html/README.md

# Copy build artifacts from builder
COPY --chown=nginx:nginx --from=builder /app/dist/assets /usr/share/nginx/html/assets
COPY --chown=nginx:nginx --from=builder /app/dist/download-metadata.json.template /usr/share/nginx/html/

# Switch back to the unprivileged user before running
USER nginx

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
