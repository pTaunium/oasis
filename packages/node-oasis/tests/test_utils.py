from __future__ import annotations

from pathlib import Path

from node_oasis.utils import calculate_sha256


def test_calculate_sha256(tmp_path: Path):
    p = tmp_path / "test.txt"
    p.write_text("hello world", encoding="utf-8")
    assert (
        calculate_sha256(p)
        == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    )
