# oasis-workspace 🏝️

[![CI](https://github.com/ptaunium/oasis/actions/workflows/ci.yml/badge.svg)](https://github.com/ptaunium/oasis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A monorepo workspace for building lightweight, self-contained offline distribution mirrors designed for air-gapped and restricted enterprise environments.

## Packages

| Package                                 | Upstream                            | Target Tooling                                                             | Documentation                                                  |
| --------------------------------------- | ----------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **[`uv-oasis`](packages/uv-oasis)**     | `astral-sh/python-build-standalone` | [`uv`](https://docs.astral.sh/uv/)                                         | [packages/uv-oasis/README.md](packages/uv-oasis/README.md)     |
| **[`node-oasis`](packages/node-oasis)** | `nodejs.org/dist/`                  | [NVM](https://github.com/nvm-sh/nvm), [fnm](https://github.com/Schniz/fnm) | [packages/node-oasis/README.md](packages/node-oasis/README.md) |

---

## Development & Quality Gate

Requires Python 3.14+ and [`uv`](https://docs.astral.sh/uv/).

### Setup

```bash
uv sync
```

### Quality Gate

All four commands must pass before commit:

```bash
uv run ruff format --check packages/
uv run ruff check packages/
uv run ty check --project packages/uv-oasis && uv run ty check --project packages/node-oasis
uv run --package uv-oasis pytest packages/uv-oasis/tests/ --cov --cov-report=term-missing
uv run --package node-oasis pytest packages/node-oasis/tests/ --cov --cov-report=term-missing
```

---

## Package Details

For package-specific configuration (`config.toml`), build flags, client configuration, and air-gapped deployment instructions:

- Python mirror: [packages/uv-oasis/README.md](packages/uv-oasis/README.md)
- Node.js mirror: [packages/node-oasis/README.md](packages/node-oasis/README.md)
- Agent guides: [AGENTS.md](AGENTS.md), [packages/uv-oasis/AGENTS.md](packages/uv-oasis/AGENTS.md), [packages/node-oasis/AGENTS.md](packages/node-oasis/AGENTS.md)

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
