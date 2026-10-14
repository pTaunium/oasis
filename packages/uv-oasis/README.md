# uv-oasis 🏝️

[![Build uv-oasis](https://github.com/ptaunium/uv-oasis/actions/workflows/build-uv-oasis.yml/badge.svg)](https://github.com/ptaunium/uv-oasis/actions/workflows/build-uv-oasis.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Drop-in offline mirror for [uv](https://docs.astral.sh/uv/)**. Serve Python binaries seamlessly in air-gapped and restricted network environments.

Downloads selected [python-build-standalone](https://github.com/astral-sh/python-build-standalone) distributions, packages them into a Docker image with nginx, and serves them as a drop-in replacement for uv's default Python download source.

## Supported Python Versions

The mirror dynamically tracks the **latest stable patch** for **all active CPython minor versions** provided by upstream [astral-sh/uv](https://github.com/astral-sh/uv) (e.g., 3.8 through 3.14+). New minor versions are supported automatically as soon as they are released upstream.

By default, the following environments are packaged:

- **Operating Systems**: Linux, Windows
- **Architecture**: `x86_64`
- **Linux libc**: `gnu`, `musl`
- **Variants**: Standard builds, and `freethreaded` (for Python 3.13+)

_(Need a different OS like macOS or architecture like `aarch64`? See the [Customization](#customization) section below.)_

## Quick Start

### Pull and run

```bash
docker run -d -p 8080:8080 \
  -e BASE_URL=http://localhost:8080 \
  --name uv-oasis \
  ghcr.io/ptaunium/uv-oasis:latest
```

### Configure uv

You can configure `uv` using an environment variable:

```bash
export UV_PYTHON_DOWNLOADS_JSON_URL=http://localhost:8080/download-metadata.json
uv python install 3.13
```

Alternatively, you can pass the URL directly via the CLI flag:

```bash
uv python install 3.13 --python-downloads-json-url http://localhost:8080/download-metadata.json
```

> **Note:** The downloaded tarballs are automatically routed to the same server via the generated JSON index, so you **do not need** to set `UV_PYTHON_INSTALL_MIRROR`.

## Air-Gapped Deployment

```bash
# 1. On a machine with internet access:
docker pull ghcr.io/ptaunium/uv-oasis:latest
docker save ghcr.io/ptaunium/uv-oasis:latest -o uv-oasis.tar

# 2. Transfer uv-oasis.tar to the air-gapped environment

# 3. On the air-gapped machine:
docker load -i uv-oasis.tar
docker run -d -p 8080:8080 \
  -e BASE_URL=http://python-mirror.internal:8080 \
  --name uv-oasis \
  ghcr.io/ptaunium/uv-oasis:latest

# 4. Configure uv on developer machines:
export UV_PYTHON_DOWNLOADS_JSON_URL=http://python-mirror.internal:8080/download-metadata.json
uv python install 3.13

# Or use the CLI flag directly:
# uv python install 3.13 --python-downloads-json-url http://python-mirror.internal:8080/download-metadata.json
```

## Docker Compose

```yaml
services:
  uv-oasis:
    image: ghcr.io/ptaunium/uv-oasis:latest
    ports:
      - "8080:8080"
    environment:
      - BASE_URL=http://python-mirror.internal:8080
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "-s", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

## Kubernetes (with Ingress)

To deploy `uv-oasis` behind a Kubernetes Ingress, you need a Deployment, a Service, and an Ingress resource.

**Awesome Feature:** The Docker container automatically configures its internal Nginx routing based on the path provided in your `BASE_URL`. If you set `BASE_URL="https://mirror.company.internal/uv-python"`, the container will automatically serve files at `/uv-python/...`. This means **you do NOT need complex rewrite rules** in your Ingress controller!

_(If your Ingress or Reverse Proxy **already strips the path**, you can set `PROXY_REWRITES_PATH: "true"` to disable this automatic internal routing.)_

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: uv-oasis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: uv-oasis
  template:
    metadata:
      labels:
        app: uv-oasis
    spec:
      containers:
        - name: uv-oasis
          image: ghcr.io/ptaunium/uv-oasis:latest
          ports:
            - containerPort: 8080
          env:
            # Set this to the exact URL the clients will use.
            # The container automatically extracts the path (/uv-python) and configures Nginx.
            - name: BASE_URL
              value: "https://mirror.company.internal/uv-python"
            # - name: PROXY_REWRITES_PATH
            #   value: "false"
          readinessProbe:
            httpGet:
              # The health check automatically adapts to the sub-path
              path: /uv-python/health
              port: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: uv-oasis
spec:
  selector:
    app: uv-oasis
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: uv-oasis
spec:
  rules:
    - host: mirror.company.internal
      http:
        paths:
          # Simple prefix match is all you need!
          - path: /uv-python
            pathType: Prefix
            backend:
              service:
                name: uv-oasis
                port:
                  number: 80
```

## Environment Variables

| Variable              | Default                 | Description                                                                                                                                                                                                                                |
| --------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `BASE_URL`            | `http://localhost:8080` | Base URL used in the JSON index. Set this to the URL that clients will use to reach the mirror.                                                                                                                                            |
| `PROXY_REWRITES_PATH` | `false`                 | Set to `true` if your external Reverse Proxy / Ingress automatically strips the sub-path (e.g., using `rewrite-target`). This tells the internal Nginx to serve files at the root `/` while still keeping the sub-path in the JSON output. |

### Client-side

> **Note:** This feature requires **uv >= 0.9.10** (support for HTTP/HTTPS URLs was introduced in 0.9.10).

| Variable                       | Description                                                                  |
| ------------------------------ | ---------------------------------------------------------------------------- |
| `UV_PYTHON_DOWNLOADS_JSON_URL` | Set to `http://<mirror-host>:8080/download-metadata.json` to use the mirror. |

## Customization

You can control exactly which Python versions, architectures, and variants are downloaded by editing the **[`config.toml`](config.toml)** file.

- **`python_variants`**: Add `"freethreaded"` to download PEP 703 free-threaded builds, or keep `"default"` for standard builds.
- **`platforms`**: Add or remove platforms (e.g., `os = "darwin"`, `arch = "aarch64"`) to support M-series Macs or ARM servers.

When you modify this file and push to GitHub, the CI/CD pipeline will automatically build a new Docker image containing your selected Python distributions!

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Docker Image (nginx:alpine)                     │
│                                                  │
│  /download-metadata.json ← JSON index            │
│  /assets/*.tar.gz        ← Python tarballs       │
│  /health                 ← Health check endpoint │
│                                                  │
│  entrypoint.sh: replaces {{BASE_URL}} at startup │
└──────────────────────────────────────────────────┘

Client (uv):
  UV_PYTHON_DOWNLOADS_JSON_URL=http://mirror:8080/download-metadata.json
  → uv reads JSON → downloads tar.gz from same server
```

## Building from Source

### Option 1: From workspace root (Recommended)

```bash
# Preview what will be downloaded
uv run --package uv-oasis python packages/uv-oasis/build.py --dry-run

# Build (download tarballs + generate JSON)
uv run --package uv-oasis python packages/uv-oasis/build.py --output ./dist

# Build Docker image (context MUST be workspace root for monorepo uv.lock bind mount)
docker build -f packages/uv-oasis/docker/Dockerfile -t uv-oasis:latest .
```

### Option 2: From package directory (`packages/uv-oasis/`)

```bash
cd packages/uv-oasis

# Preview or build
uv run python build.py --dry-run
uv run python build.py --output ./dist

# Build using a specific config file or metadata URL (optional)
# uv run python build.py --output ./dist --config custom.toml --metadata-url "https://raw.githubusercontent.com/astral-sh/uv/some-branch/crates/uv-python-managed/download-metadata.json"

# Build Docker image (context must still point to workspace root)
docker build -f docker/Dockerfile -t uv-oasis:latest ../..
```

## API Endpoints

| Endpoint                  | Method | Description                                               |
| ------------------------- | ------ | --------------------------------------------------------- |
| `/download-metadata.json` | GET    | JSON index compatible with `UV_PYTHON_DOWNLOADS_JSON_URL` |
| `/assets/{filename}`      | GET    | Python standalone build tarballs                          |
| `/health`                 | GET    | Returns `200 ok` for health checks                        |

## License & Credits

This project downloads and redistributes binaries from:

- **[python-build-standalone](https://github.com/astral-sh/python-build-standalone)** by [Astral](https://astral.sh/) — Licensed under the [Python Software Foundation License](https://docs.python.org/3/license.html).
- **[uv](https://github.com/astral-sh/uv)** by [Astral](https://astral.sh/) — The JSON metadata format is derived from uv's `download-metadata.json`.

This project itself is licensed under the MIT License. See [LICENSE](LICENSE) for details.
