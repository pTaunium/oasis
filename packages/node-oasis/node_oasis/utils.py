"""Common utility functions for node-oasis."""

from __future__ import annotations

import hashlib
from pathlib import Path

_PLATFORM_ALIASES: dict[str, str] = {
    "osx-arm64": "darwin-arm64",
    "osx-x64": "darwin-x64",
    "darwin-aarch64": "darwin-arm64",
    "linux-aarch64": "linux-arm64",
    "win-ia32": "win-x86",
    "win32": "win-x86",
    "windows-x64": "win-x64",
    "windows-arm64": "win-arm64",
    "windows-x86": "win-x86",
}


def normalize_platform(platform: str) -> str:
    """Normalize user/config platform alias to canonical upstream archive platform name."""
    clean = platform.strip().lower()
    return _PLATFORM_ALIASES.get(clean, clean)


def calculate_sha256(path: Path) -> str:
    """Calculate the SHA256 checksum of a file using Python 3.11+ file_digest."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
