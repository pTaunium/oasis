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


def _filter_index_tab(raw_tab: str, versions: set[str]) -> str:
    """Filter index.tab lines to only include versions in the set, preserving the header."""
    lines = raw_tab.splitlines()
    if not lines:
        return ""

    filtered = [lines[0]]  # Header line
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts[0] in versions:
            filtered.append(line)

    return "\n".join(filtered) + "\n"


def write_index_tab(raw_tab: str, versions: set[str], output_path: Path) -> Path:
    """Filter and write index.tab."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered = _filter_index_tab(raw_tab, versions)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(filtered)
    return output_path
