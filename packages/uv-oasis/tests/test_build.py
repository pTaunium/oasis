from __future__ import annotations

import logging
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from build import main
from uv_oasis.models import MetadataEntry, MetadataIndex


def test_main_dry_run(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    mock_metadata: MetadataIndex = {
        "cpython-3.12.0-x86_64-unknown-linux-gnu-install_only": {
            "name": "cpython",
            "arch": {"family": "x86_64", "variant": None},
            "os": "linux",
            "libc": "gnu",
            "major": 3,
            "minor": 12,
            "patch": 0,
            "prerelease": "",
            "url": "https://example.com/py.tar.gz",
            "sha256": "fakehash",
        }
    }

    monkeypatch.setattr("build.fetch_metadata", lambda **kwargs: mock_metadata)
    monkeypatch.setattr(
        "build.filter_entries",
        lambda metadata, config: {
            "cpython-3.12.0-x86_64-unknown-linux-gnu-install_only": {
                "name": "cpython",
                "variant": "default",
            }
        },
    )

    caplog.set_level(logging.INFO)
    exit_code = main(["--dry-run"])
    assert exit_code == 0
    assert "Dry run" in caplog.text


def test_main_custom_metadata_url(
    monkeypatch: pytest.MonkeyPatch,
):
    received_kwargs: dict[str, object] = {}

    def mock_fetch(**kwargs: object) -> MetadataIndex:
        received_kwargs.update(kwargs)
        return {}

    monkeypatch.setattr("build.fetch_metadata", mock_fetch)
    monkeypatch.setattr("build.filter_entries", lambda metadata, config: {})

    exit_code = main(["--metadata-url", "https://custom.test/meta.json", "--dry-run"])
    assert exit_code == 0
    assert received_kwargs["url"] == "https://custom.test/meta.json"


def test_main_full_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mock_entry: MetadataEntry = {
        "name": "cpython",
        "arch": {"family": "x86_64", "variant": None},
        "os": "linux",
        "libc": "gnu",
        "major": 3,
        "minor": 12,
        "patch": 0,
        "prerelease": "",
        "url": "https://example.com/py.tar.gz",
        "sha256": "fakehash",
    }
    mock_metadata: MetadataIndex = {
        "cpython-3.12.0-x86_64-unknown-linux-gnu-install_only": mock_entry
    }

    monkeypatch.setattr("build.fetch_metadata", lambda **kwargs: mock_metadata)
    monkeypatch.setattr(
        "build.filter_entries",
        lambda metadata, config: {
            "cpython-3.12.0-x86_64-unknown-linux-gnu-install_only": mock_entry
        },
    )

    downloaded_tarballs: list[object] = []
    index_written: list[Path] = []

    def mock_download(entries: MetadataIndex, dest: Path) -> list[Path]:
        downloaded_tarballs.append(entries)
        return []

    def mock_write_index(entries: MetadataIndex, dest: Path) -> Path:
        index_written.append(dest)
        return dest

    monkeypatch.setattr("build.download_tarballs", mock_download)
    monkeypatch.setattr("build.write_json_index", mock_write_index)

    out_dir = tmp_path / "output"
    exit_code = main(["--output", str(out_dir)])

    assert exit_code == 0
    assert len(downloaded_tarballs) == 1
    assert len(index_written) == 1
    assert index_written[0] == out_dir / "download-metadata.json.template"


def test_main_entrypoint():
    import build

    with (
        patch.object(sys, "argv", ["build.py", "--dry-run"]),
        patch("build.fetch_metadata", return_value={}),
        patch("build.filter_entries", return_value={}),
        pytest.raises(SystemExit) as exc_info,
    ):
        runpy.run_path(str(Path(build.__file__)), run_name="__main__")
    assert exc_info.value.code == 0
