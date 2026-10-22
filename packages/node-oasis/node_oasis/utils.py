"""Common utility functions for node-oasis."""

from __future__ import annotations

import hashlib
from pathlib import Path


def calculate_sha256(path: Path) -> str:
    """Calculate the SHA256 checksum of a file using Python 3.11+ file_digest."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
