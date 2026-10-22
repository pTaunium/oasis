"""Generate index.json and index.tab for mirrored releases."""

from __future__ import annotations

import json
from pathlib import Path

from .models import NodeIndex


def write_index_json(releases: NodeIndex, output_path: Path) -> Path:
    """Write the filtered releases as a JSON array."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(releases, f, indent=2)
        f.write("\n")
    return output_path


def write_index_tab(content: str, output_path: Path) -> Path:
    """Write index.tab content to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(content)
    return output_path
