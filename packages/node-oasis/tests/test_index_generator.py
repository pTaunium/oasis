from __future__ import annotations

import json
from pathlib import Path

from node_oasis.index_generator import (
    _filter_index_tab,
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


def test_filter_index_tab_empty():
    assert _filter_index_tab("", {"v22.14.0"}) == ""


def test_filter_index_tab():
    raw_tab = """version\tdate\tfpm\tnpm\tv8\tuv\tzlib\topenssl\tmodules\tlts\tsecurity
v22.14.0\t2025-02-18\t\t10.9.2\t12.4.254.21\t1.49.2\t1.3.0.1\t3.0.15\t127\tJod\tfalse
v22.13.0\t2025-01-20\t\t10.9.0\t12.4.254.20\t1.49.0\t1.3.0.1\t3.0.15\t127\tfalse\tfalse
v20.18.1\t2024-11-20\t\t10.8.2\t11.3.244.8\t1.48.0\t1.3.0.1\t3.0.15\t115\tIron\tfalse

"""
    versions = {"v22.14.0", "v20.18.1"}
    filtered = _filter_index_tab(raw_tab, versions)

    lines = [line for line in filtered.splitlines() if line.strip()]
    assert len(lines) == 3
    assert lines[0].startswith("version\tdate")
    assert lines[1].startswith("v22.14.0\t")
    assert lines[2].startswith("v20.18.1\t")


def test_write_index_tab(tmp_path: Path):
    raw_tab = "version\tdate\nv22.14.0\t2025-02-18\nv20.0.0\t2023-04-18\n"
    out_file = tmp_path / "dist" / "index.tab"

    result = write_index_tab(raw_tab, {"v22.14.0"}, out_file)
    assert result == out_file
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "v22.14.0" in content
    assert "v20.0.0" not in content
