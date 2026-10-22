from __future__ import annotations

import logging
from pathlib import Path

import pytest
from build import main
from node_oasis.models import NodeIndex


def test_main_validation_no_versions(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0
    captured = capsys.readouterr()
    assert (
        "At least one of --versions or --latest-lts must be specified" in captured.err
    )


def test_main_validation_mutually_exclusive_tools(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        main(["--latest-lts", "--tools", "fnm", "--no-tools"])
    assert exc.value.code != 0
    captured = capsys.readouterr()
    assert "--tools and --no-tools are mutually exclusive" in captured.err

    with pytest.raises(SystemExit) as exc:
        main(["--latest-lts", "--tools", "nvm", "fnm", "--no-tools"])
    assert exc.value.code != 0
    captured = capsys.readouterr()
    assert "--tools and --no-tools are mutually exclusive" in captured.err


def test_main_validation_invalid_tool(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        main(["--latest-lts", "--tools", "invalid"])
    assert exc.value.code != 0
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err


def test_main_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    mock_catalog = {
        "releases": [
            {"version": "v22.14.0", "lts": "Jod", "files": ["linux-x64"]},
            {"version": "v20.18.1", "lts": "Iron", "files": ["linux-x64"]},
        ],
        "index_tab_content": "version\tdate\n",
        "target_versions": ["22"],
    }

    monkeypatch.setattr("build.resolve_catalog", lambda **kwargs: mock_catalog)

    exit_code = main(["--latest-lts", "--dry-run"])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "v22.14.0" in captured.out
    assert "nvm: latest" in captured.out
    assert "fnm: latest" in captured.out


def test_main_full_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mock_catalog = {
        "releases": [{"version": "v22.14.0", "lts": "Jod", "files": ["linux-x64"]}],
        "index_tab_content": "version\tdate\nv22.14.0\t2025-02-18\n",
        "target_versions": ["22"],
    }

    monkeypatch.setattr("build.resolve_catalog", lambda **kwargs: mock_catalog)

    downloaded_releases: list[object] = []
    downloaded_tools: list[str] = []
    received_tool_kwargs: dict[str, object] = {}
    received_release_kwargs: dict[str, object] = {}

    def mock_download_releases(
        releases: NodeIndex, out_dir: Path, **kwargs: object
    ) -> list[Path]:
        downloaded_releases.extend(releases)
        received_release_kwargs.update(kwargs)
        return []

    def mock_download_tools(
        out_dir: Path, tools: list[str] | None = None, **kwargs: object
    ) -> None:
        if tools:
            downloaded_tools.extend(tools)
        received_tool_kwargs.update(kwargs)

    monkeypatch.setattr("build.download_node_releases", mock_download_releases)
    monkeypatch.setattr("build.download_tools", mock_download_tools)

    cfg_file = tmp_path / "custom_config.toml"
    cfg_file.write_text(
        """
[upstream]
platform = "linux-x64"

[tools]
nvm_api_url = "https://custom.internal/nvm"
fnm_api_url = "https://custom.internal/fnm"
""",
        encoding="utf-8",
    )

    out_dir = tmp_path / "output"
    exit_code = main(
        [
            "--versions",
            "22",
            "--output",
            str(out_dir),
            "--tools",
            "fnm",
            "--platform",
            "linux-x64",
            "--config",
            str(cfg_file),
        ]
    )

    assert exit_code == 0
    assert len(downloaded_releases) == 1
    assert downloaded_tools == ["fnm"]
    assert received_release_kwargs["platforms"] == ["linux-x64"]
    assert received_tool_kwargs["fnm_api_url"] == "https://custom.internal/fnm"
    assert received_tool_kwargs["nvm_api_url"] == "https://custom.internal/nvm"
    assert (out_dir / "dist" / "index.json").exists()
    assert (out_dir / "dist" / "index.tab").exists()
    assert (out_dir / "tools").exists()


def test_main_full_run_no_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mock_catalog = {
        "releases": [{"version": "v22.14.0", "lts": "Jod", "files": ["linux-x64"]}],
        "index_tab_content": "version\tdate\nv22.14.0\t2025-02-18\n",
        "target_versions": ["22"],
    }
    monkeypatch.setattr("build.resolve_catalog", lambda **kwargs: mock_catalog)
    monkeypatch.setattr("build.download_node_releases", lambda *args, **kwargs: [])

    out_dir = tmp_path / "output_no_tools"
    exit_code = main(["--versions", "22", "--output", str(out_dir), "--no-tools"])

    assert exit_code == 0
    assert (out_dir / "dist" / "index.json").exists()
    assert (out_dir / "tools").exists()


def test_main_no_matching_releases(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(
        "build.resolve_catalog",
        lambda **kwargs: {
            "releases": [],
            "index_tab_content": "",
            "target_versions": ["99"],
        },
    )

    caplog.set_level(logging.ERROR)
    exit_code = main(["--versions", "99", "--dry-run"])
    assert exit_code == 1
    assert "No Node.js releases matched target versions" in caplog.text


def test_main_entrypoint():
    import runpy
    import sys
    from unittest.mock import patch

    import build

    mock_catalog = {
        "releases": [{"version": "v22.14.0", "lts": "Jod", "files": ["linux-x64"]}],
        "index_tab_content": "",
        "target_versions": ["22"],
    }

    with (
        patch.object(sys, "argv", ["build.py", "--latest-lts", "--dry-run"]),
        patch("build.resolve_catalog", return_value=mock_catalog),
        pytest.raises(SystemExit) as exc_info,
    ):
        runpy.run_path(str(Path(build.__file__)), run_name="__main__")
    assert exc_info.value.code == 0
