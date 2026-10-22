from __future__ import annotations

from pathlib import Path

from node_oasis.config import (
    DEFAULT_FNM_API_URL,
    DEFAULT_NODEJS_DIST_URL,
    DEFAULT_NVM_API_URL,
    DEFAULT_PLATFORM,
    DEFAULT_PLATFORMS,
    DEFAULT_SCHEDULE_URL,
    load_config,
)


def test_load_config_missing_file(tmp_path: Path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg["upstream"]["nodejs_dist_url"] == DEFAULT_NODEJS_DIST_URL
    assert cfg["upstream"]["schedule_url"] == DEFAULT_SCHEDULE_URL
    assert cfg["upstream"]["platform"] == DEFAULT_PLATFORM
    assert cfg["upstream"]["platforms"] == DEFAULT_PLATFORMS
    assert cfg["tools"]["nvm_api_url"] == DEFAULT_NVM_API_URL
    assert cfg["tools"]["fnm_api_url"] == DEFAULT_FNM_API_URL


def test_load_config_empty_file(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text("", encoding="utf-8")
    cfg = load_config(p)
    assert cfg["upstream"]["nodejs_dist_url"] == DEFAULT_NODEJS_DIST_URL
    assert cfg["upstream"]["platform"] == DEFAULT_PLATFORM
    assert cfg["upstream"]["platforms"] == DEFAULT_PLATFORMS
    assert cfg["tools"]["nvm_api_url"] == DEFAULT_NVM_API_URL


def test_load_config_full(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        """
[upstream]
nodejs_dist_url = "https://custom.mirror/dist"
schedule_url = "https://custom.mirror/schedule.json"
platforms = ["linux-arm64", "darwin-arm64"]

[tools]
nvm_api_url = "https://custom.github.internal/nvm"
fnm_api_url = "https://custom.github.internal/fnm"
nvm_sha256 = "fake-nvm-sha"
fnm_sha256 = { "fnm-arm64.zip" = "fake-fnm-sha" }
""",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg["upstream"]["nodejs_dist_url"] == "https://custom.mirror/dist"
    assert cfg["upstream"]["schedule_url"] == "https://custom.mirror/schedule.json"
    assert cfg["upstream"]["platform"] == "linux-arm64"
    assert cfg["upstream"]["platforms"] == ["linux-arm64", "darwin-arm64"]
    assert cfg["tools"]["nvm_api_url"] == "https://custom.github.internal/nvm"
    assert cfg["tools"]["fnm_api_url"] == "https://custom.github.internal/fnm"
    assert cfg["tools"]["nvm_sha256"] == "fake-nvm-sha"
    assert cfg["tools"]["fnm_sha256"] == {"fnm-arm64.zip": "fake-fnm-sha"}


def test_load_config_trailing_slash_stripped(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        """
[upstream]
nodejs_dist_url = "https://custom.mirror/dist/"
""",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg["upstream"]["nodejs_dist_url"] == "https://custom.mirror/dist"
