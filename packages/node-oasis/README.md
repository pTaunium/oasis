# node-oasis 🏝️

[![Build node-oasis](https://github.com/ptaunium/oasis/actions/workflows/build-node-oasis.yml/badge.svg)](https://github.com/ptaunium/oasis/actions/workflows/build-node-oasis.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Drop-in offline Node.js distribution mirror for NVM and fnm**. Designed for air-gapped environments and enterprise networks.

Downloads selected Node.js distributions from `nodejs.org`, packages them into a Docker image with Nginx, and serves them as a drop-in replacement for `nodejs.org/dist/`. In addition, it bundles offline installation scripts and binaries for popular Node.js version managers ([NVM](https://github.com/nvm-sh/nvm) and [fnm](https://github.com/Schniz/fnm)), enabling seamless zero-internet bootstrapping and runtime version switching.

---

## How It Works

1. **Fetches Metadata**: Reads upstream distribution metadata (`index.json`, `index.tab`) from `nodejs.org/dist/` and release schedules from the official Node.js release schedule repository.
2. **Filters Versions**: Retains only the latest patch for target major versions (e.g. Active/Maintenance LTS versions or custom-specified major versions).
3. **Downloads Binaries & Checksums**: Downloads Node.js release tarballs (`.tar.xz`), `SHASUMS256.txt`, and cryptographic signatures (`SHASUMS256.txt.asc`), verifying SHA256 hashes.
4. **Generates Mirror Indices**: Writes filtered `index.json` (for fnm) and `index.tab` (for NVM) preserving the exact upstream schema without needing URL rewrites.
5. **Bundles Version Managers**: Fetches and bundles standalone installers for NVM and fnm along with wrapper setup scripts (`setup-nvm.sh`, `setup-fnm.sh`).
6. **Serves via Nginx**: Packages everything into a lightweight non-root Nginx container configured to automatically handle arbitrary base URLs and reverse-proxy paths.

---

## Quick Start

### 1. Build the Mirror Assets

From workspace root (Recommended):

```bash
# Download latest Active and Maintenance LTS versions into ./dist
uv run --package node-oasis python packages/node-oasis/build.py --latest-lts --output ./dist
```

Or from `packages/node-oasis/`:

```bash
cd packages/node-oasis
uv run python build.py --latest-lts --output ./dist
```

### 2. Build and Run the Docker Image

```bash
# Build Docker image (context MUST be workspace root for monorepo uv.lock bind mount)
docker build -f packages/node-oasis/docker/Dockerfile -t node-oasis:latest .

# Run the container
docker run -d -p 8080:8080 \
  -e BASE_URL=http://localhost:8080 \
  --name node-oasis \
  node-oasis:latest
```

---

## Client Configuration

Once `node-oasis` is running, configure your Node version manager to point to the mirror's `/dist` endpoint:

### NVM

```bash
export NVM_NODEJS_ORG_MIRROR="http://your-mirror:8080/dist"
nvm install 22
```

To make this permanent, add the environment variable to your shell configuration (`~/.bashrc`, `~/.zshrc`):

```bash
echo 'export NVM_NODEJS_ORG_MIRROR="http://your-mirror:8080/dist"' >> ~/.bashrc
```

### fnm

```bash
export FNM_NODE_DIST_MIRROR="http://your-mirror:8080/dist"
fnm install 22
```

To make this permanent, add the export to your shell configuration:

```bash
echo 'export FNM_NODE_DIST_MIRROR="http://your-mirror:8080/dist"' >> ~/.bashrc
```

---

## Air-Gapped NVM / fnm Installation

In strictly air-gapped environments where developer workstations do not have NVM or fnm installed yet, `node-oasis` serves self-contained installer wrappers:

### Install NVM

```bash
curl -fsSL http://your-mirror:8080/tools/nvm/setup-nvm.sh | bash
```

The `setup-nvm.sh` script installs NVM from the offline tarball hosted on the mirror and automatically configures `NVM_NODEJS_ORG_MIRROR` to point to the mirror.

### Install fnm

```bash
curl -fsSL http://your-mirror:8080/tools/fnm/setup-fnm.sh | bash
```

The `setup-fnm.sh` script downloads the standalone `fnm` binary from the mirror, installs it into `~/.local/share/fnm`, and sets up shell completions and environment variables.

---

## Air-Gapped Deployment Guide

```bash
# 1. On an internet-connected machine:
# Build Docker image (from workspace root; build.py runs inside Stage 1 builder)
docker build -f packages/node-oasis/docker/Dockerfile -t node-oasis:latest .
docker save node-oasis:latest -o node-oasis.tar

# 2. Transfer node-oasis.tar to the air-gapped environment (e.g. via USB or internal registry)

# 3. On the air-gapped host:
docker load -i node-oasis.tar
docker run -d -p 8080:8080 \
  -e BASE_URL=http://node-mirror.internal:8080 \
  --name node-oasis \
  node-oasis:latest

# 4. On client machines:
curl -fsSL http://node-mirror.internal:8080/tools/nvm/setup-nvm.sh | bash
nvm install 22
```

---

## Docker Compose

```yaml
services:
  node-oasis:
    image: node-oasis:latest
    ports:
      - "8080:8080"
    environment:
      - BASE_URL=http://node-mirror.internal:8080
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "-s", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

---

## Kubernetes (with Ingress)

The container automatically configures internal Nginx routing according to the URL path in `BASE_URL`. For example, setting `BASE_URL="https://mirror.company.internal/node"` routes requests under `/node/...` directly to the mirror files without requiring rewrite annotations in your Ingress.

*(If your Ingress or Reverse Proxy already strips the sub-path prefix, set `PROXY_REWRITES_PATH="true"`.)*

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: node-oasis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: node-oasis
  template:
    metadata:
      labels:
        app: node-oasis
    spec:
      containers:
        - name: node-oasis
          image: node-oasis:latest
          ports:
            - containerPort: 8080
          env:
            - name: BASE_URL
              value: "https://mirror.company.internal/node"
            # Set to "true" only if reverse proxy strips the "/node" prefix
            # - name: PROXY_REWRITES_PATH
            #   value: "true"
          readinessProbe:
            httpGet:
              path: /node/health
              port: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: node-oasis
spec:
  selector:
    app: node-oasis
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: node-oasis
spec:
  rules:
    - host: mirror.company.internal
      http:
        paths:
          - path: /node
            pathType: Prefix
            backend:
              service:
                name: node-oasis
                port:
                  number: 80
```

---

## Mirror Directory Structure

```
http://your-mirror:8080/
├── dist/
│   ├── index.json                              ← Filtered index for fnm
│   ├── index.tab                               ← Filtered index for NVM
│   ├── v20.18.3/
│   │   ├── node-v20.18.3-linux-x64.tar.xz      ← Node.js distribution tarball
│   │   ├── SHASUMS256.txt                      ← SHA256 checksums
│   │   └── SHASUMS256.txt.asc                  ← GPG signature
│   ├── v22.14.0/
│   │   └── ...
│   └── v24.1.0/
│       └── ...
├── tools/
│   ├── nvm/
│   │   ├── install.sh                          ← Upstream NVM install script
│   │   ├── nvm-v0.40.3.tar.gz                  ← NVM source tarball
│   │   └── setup-nvm.sh                        ← Air-gapped wrapper script
│   └── fnm/
│       ├── fnm-linux-v1.39.0.zip               ← fnm binary archive
│       └── setup-fnm.sh                        ← Air-gapped wrapper script
└── health                                      ← Health check endpoint
```

---

## CLI Usage

The build script `build.py` handles downloading distributions, verifying checksums, creating indices, and bundling tools:

```bash
uv run python build.py [OPTIONS]
```

### Options

| Option | Type | Description |
|---|---|---|
| `--latest-lts` | flag | Automatically include all Active and Maintenance LTS versions from the official release schedule. |
| `--versions` | list of str | Specific Node.js major or exact versions to download (e.g. `20 22.14.0`). For major versions, keeps the latest stable patch. |
| `--platforms` | list of str | Target platform identifiers (e.g. `linux-x64 darwin-arm64`). Default: `linux-x64`. |
| `--output`, `-o` | path | Target output directory (required unless `--dry-run` is used). |
| `--tools` | list of str | Tools to download and package (`nvm`, `fnm`). Default: both. |
| `--no-tools` | flag | Disable tool downloading entirely. |
| `--dry-run` | flag | Display the download execution plan in tabular format without downloading. |
| `--config` | path | Path to configuration file (default: `config.toml`). |

### Examples

```bash
# 1. Download all active and maintenance LTS versions (default: includes nvm and fnm)
uv run python build.py --latest-lts --output ./dist

# 2. Download specific major versions
uv run python build.py --versions 20 22 24 --output ./dist

# 3. Combine LTS with a specific non-LTS or upcoming version
uv run python build.py --latest-lts --versions 23 --output ./dist

# 4. Preview downloads without downloading anything
uv run python build.py --latest-lts --dry-run

# 5. Download only fnm tool (omit nvm)
uv run python build.py --latest-lts --output ./dist --tools fnm

# 6. Build without any tools
uv run python build.py --latest-lts --output ./dist --no-tools

# 7. Use a custom configuration file
uv run python build.py --latest-lts --output ./dist --config custom.toml
```

---

## Environment Variables

### Server-side (Container)

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8080` | Public URL clients use to access the mirror. Used for Nginx routing and injected into `setup-nvm.sh` / `setup-fnm.sh`. |
| `PROXY_REWRITES_PATH` | `false` | Set to `true` if an external reverse proxy / Ingress controller strips the path prefix before forwarding traffic to Nginx. |

### Client-side

| Variable | Description |
|---|---|
| `NVM_NODEJS_ORG_MIRROR` | Set to `http://<mirror-host>:8080/dist` for NVM. |
| `FNM_NODE_DIST_MIRROR` | Set to `http://<mirror-host>:8080/dist` for fnm. |

---

## Development

Prerequisites: Python 3.14+ and [`uv`](https://docs.astral.sh/uv/).

From workspace root:

```bash
# Run tests with coverage
uv run --package node-oasis pytest packages/node-oasis/tests/ --cov --cov-report=term-missing

# Format and lint
uv run ruff format --check packages/ && uv run ruff check packages/

# Type check
uv run ty check --project packages/node-oasis
```

---

## License & Credits

This project downloads and redistributes binaries and software from:

- **[Node.js](https://nodejs.org/)** — Licensed under the [Node.js License](https://raw.githubusercontent.com/nodejs/node/main/LICENSE).
- **[nvm-sh/nvm](https://github.com/nvm-sh/nvm)** — Licensed under the [MIT License](https://github.com/nvm-sh/nvm/blob/master/LICENSE.markdown).
- **[Schniz/fnm](https://github.com/Schniz/fnm)** — Licensed under the [GPL-3.0 License](https://github.com/Schniz/fnm/blob/master/LICENSE).

This project itself is licensed under the MIT License. See [LICENSE](../../LICENSE) for details.
