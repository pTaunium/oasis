from __future__ import annotations

import json
from pathlib import Path

from node_oasis.index_generator import (
    write_index_json,
    write_index_tab,
)
from node_oasis.models import NodeIndex


def test_write_index_json(tmp_path: Path):
    releases: NodeIndex = [
        {"version": "v22.14.0", "lts": "Jod", "files": ["linux-x64"]},
        {"version": "v20.18.1", "lts": "Iron", "files": ["linux-x64"]},
    ]
    out_file = tmp_path / "dist" / "index.json"
    result = write_index_json(releases, out_file)

    assert result == out_file
    assert out_file.exists()

    with out_file.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == releases


def test_write_index_tab(tmp_path: Path):
    tab_content = "version\tdate\nv22.14.0\t2025-02-18\n"
    out_file = tmp_path / "dist" / "index.tab"

    result = write_index_tab(tab_content, out_file)
    assert result == out_file
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert content == tab_content
