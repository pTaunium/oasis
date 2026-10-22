from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from node_oasis.models import ChecksumMismatchError, FnmReleaseInfo, NvmReleaseInfo
from node_oasis.tools import (
    FNM_API_URL,
    NVM_API_URL,
    _get_latest_release_info,
    _is_retryable_tool_error,
    download_fnm,
    download_nvm,
    download_tools,
    generate_setup_scripts,
)


@respx.mock
def test_get_latest_release_info_nvm():
    respx.get(NVM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v0.40.3",
                "tarball_url": "https://api.github.com/repos/nvm-sh/nvm/tarball/v0.40.3",
            },
        )
    )

    with httpx.Client() as client:
        info = _get_latest_release_info(client, NVM_API_URL)

    assert info["version"] == "v0.40.3"
    assert "v0.40.3" in info["download_url"]


@respx.mock
def test_get_latest_release_info_with_auth_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_TOKEN", "mock-token-xyz")
    route = respx.get(NVM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v0.40.3",
                "tarball_url": "https://api.github.com/repos/nvm-sh/nvm/tarball/v0.40.3",
            },
        )
    )

    with httpx.Client() as client:
        info = _get_latest_release_info(client, NVM_API_URL)

    assert info["version"] == "v0.40.3"
    assert route.calls.last.request.headers["authorization"] == "Bearer mock-token-xyz"


@respx.mock
def test_download_nvm(tmp_path: Path):
    respx.get(NVM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v0.40.3",
                "tarball_url": "https://github.com/nvm-sh/nvm/archive/v0.40.3.tar.gz",
            },
        )
    )
    respx.get("https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh").mock(
        return_value=httpx.Response(200, content=b"#!/bin/bash echo nvm install")
    )
    respx.get("https://github.com/nvm-sh/nvm/archive/v0.40.3.tar.gz").mock(
        return_value=httpx.Response(200, content=b"fake-nvm-tarball-bytes")
    )

    with httpx.Client() as client:
        result = download_nvm(client, tmp_path)

    assert result["version"] == "v0.40.3"
    assert result["tarball_filename"] == "nvm-v0.40.3.tar.gz"
    assert (tmp_path / "nvm" / "install.sh").exists()
    assert (tmp_path / "nvm" / "nvm-v0.40.3.tar.gz").exists()


@respx.mock
def test_download_fnm(tmp_path: Path):
    respx.get(FNM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v1.38.1",
                "assets": [
                    {
                        "name": "fnm-linux.zip",
                        "browser_download_url": "https://github.com/Schniz/fnm/releases/download/v1.38.1/fnm-linux.zip",
                    }
                ],
            },
        )
    )
    respx.get(
        "https://github.com/Schniz/fnm/releases/download/v1.38.1/fnm-linux.zip"
    ).mock(return_value=httpx.Response(200, content=b"fake-fnm-zip-bytes"))

    with httpx.Client() as client:
        result = download_fnm(client, tmp_path)

    assert result["version"] == "v1.38.1"
    assert result["zip_filename"] == "fnm-linux-v1.38.1.zip"
    assert (tmp_path / "fnm" / "fnm-linux-v1.38.1.zip").exists()


def test_generate_setup_scripts(tmp_path: Path):
    nvm_info: NvmReleaseInfo = {
        "version": "v0.40.3",
        "tarball_filename": "nvm-v0.40.3.tar.gz",
    }
    fnm_info: FnmReleaseInfo = {
        "version": "v1.38.1",
        "zip_filename": "fnm-linux-v1.38.1.zip",
    }

    scripts = generate_setup_scripts(tmp_path, nvm_info=nvm_info, fnm_info=fnm_info)

    assert len(scripts) == 2
    nvm_script = tmp_path / "nvm" / "setup-nvm.sh.template"
    fnm_script = tmp_path / "fnm" / "setup-fnm.sh.template"

    assert nvm_script.exists()
    assert fnm_script.exists()

    nvm_content = nvm_script.read_text(encoding="utf-8")
    assert "{{BASE_URL}}/tools/nvm/nvm-v0.40.3.tar.gz" in nvm_content
    assert "{{BASE_URL}}/dist" in nvm_content
    assert "tar -xzf" in nvm_content
    assert "--strip-components=1" in nvm_content
    assert "NVM_NODEJS_ORG_MIRROR" in nvm_content
    assert '"${SHELL:-sh}"' in nvm_content
    assert "mktemp" in nvm_content
    assert "trap 'rm -f" in nvm_content
    assert 'touch "$PROFILE"' in nvm_content

    fnm_content = fnm_script.read_text(encoding="utf-8")
    assert "{{BASE_URL}}/tools/fnm/fnm-linux-v1.38.1.zip" in fnm_content
    assert "{{BASE_URL}}/dist" in fnm_content
    assert "mktemp" in fnm_content
    assert "trap 'rm -f" in fnm_content
    assert 'chmod +x "$FNM_DIR/fnm"' in fnm_content
    assert 'chmod +x "$FNM_DIR/fnm.exe"' in fnm_content


@respx.mock
def test_download_tools(tmp_path: Path):
    respx.get(NVM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v0.40.3",
                "tarball_url": "https://github.com/nvm-sh/nvm/archive/v0.40.3.tar.gz",
            },
        )
    )
    respx.get("https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh").mock(
        return_value=httpx.Response(200, content=b"install script")
    )
    respx.get("https://github.com/nvm-sh/nvm/archive/v0.40.3.tar.gz").mock(
        return_value=httpx.Response(200, content=b"tarball content")
    )

    download_tools(tmp_path, tools=["nvm"])

    assert (tmp_path / "nvm" / "install.sh").exists()
    assert (tmp_path / "nvm" / "setup-nvm.sh.template").exists()
    assert not (tmp_path / "fnm").exists()


@respx.mock
def test_download_tools_fnm(tmp_path: Path):
    respx.get(FNM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v1.38.1",
                "assets": [
                    {
                        "name": "fnm-linux.zip",
                        "browser_download_url": "https://download/fnm-linux.zip",
                    }
                ],
            },
        )
    )
    respx.get("https://download/fnm-linux.zip").mock(
        return_value=httpx.Response(200, content=b"fnm zip")
    )

    download_tools(tmp_path, tools=["fnm"])

    assert (tmp_path / "fnm" / "fnm-linux-v1.38.1.zip").exists()
    assert (tmp_path / "fnm" / "setup-fnm.sh.template").exists()
    assert not (tmp_path / "nvm").exists()


def test_generate_setup_scripts_none(tmp_path: Path):
    scripts = generate_setup_scripts(tmp_path, nvm_info=None, fnm_info=None)
    assert scripts == []
    assert not (tmp_path / "nvm").exists()
    assert not (tmp_path / "fnm").exists()


def test_download_tools_empty(tmp_path: Path):
    download_tools(tmp_path, tools=[])
    assert not (tmp_path / "nvm").exists()
    assert not (tmp_path / "fnm").exists()


@respx.mock
def test_download_tools_custom_api_urls(tmp_path: Path):
    custom_nvm_api = "https://custom.github.internal/nvm/latest"
    respx.get(custom_nvm_api).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v0.40.3",
                "tarball_url": "https://custom.github.internal/nvm.tar.gz",
            },
        )
    )
    respx.get("https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh").mock(
        return_value=httpx.Response(200, content=b"install script")
    )
    respx.get("https://custom.github.internal/nvm.tar.gz").mock(
        return_value=httpx.Response(200, content=b"tarball content")
    )

    download_tools(tmp_path, tools=["nvm"], nvm_api_url=custom_nvm_api)

    assert (tmp_path / "nvm" / "nvm-v0.40.3.tar.gz").exists()


def test_get_fnm_asset_name_for_platform():
    from node_oasis.tools import get_fnm_asset_name_for_platform

    assert get_fnm_asset_name_for_platform("linux-arm64") == "fnm-arm64.zip"
    assert get_fnm_asset_name_for_platform("linux-aarch64") == "fnm-arm64.zip"
    assert get_fnm_asset_name_for_platform("linux-armv7l") == "fnm-arm32.zip"
    assert get_fnm_asset_name_for_platform("linux-x64") == "fnm-linux.zip"
    assert get_fnm_asset_name_for_platform("darwin-arm64") == "fnm-macos.zip"
    assert get_fnm_asset_name_for_platform("osx-arm64") == "fnm-macos.zip"
    assert get_fnm_asset_name_for_platform("win-x64") == "fnm-windows.zip"
    assert get_fnm_asset_name_for_platform("win-ia32") == "fnm-windows.zip"
    assert get_fnm_asset_name_for_platform("unknown") == "fnm-linux.zip"


@respx.mock
def test_download_nvm_checksum_verification(tmp_path: Path):
    import hashlib

    tarball_content = b"fake-nvm-tarball-bytes"
    correct_sha = hashlib.sha256(tarball_content).hexdigest()

    respx.get(NVM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v0.40.3",
                "tarball_url": "https://github.com/nvm-sh/nvm/archive/v0.40.3.tar.gz",
            },
        )
    )
    respx.get("https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh").mock(
        return_value=httpx.Response(200, content=b"#!/bin/bash echo nvm install")
    )
    respx.get("https://github.com/nvm-sh/nvm/archive/v0.40.3.tar.gz").mock(
        return_value=httpx.Response(200, content=tarball_content)
    )

    with httpx.Client() as client:
        # Success with matching checksum
        result = download_nvm(client, tmp_path, expected_sha256=correct_sha)
        assert result["version"] == "v0.40.3"

        # Failure with mismatch checksum
        with pytest.raises(ChecksumMismatchError, match="Checksum mismatch"):
            download_nvm(client, tmp_path, expected_sha256="wrong-sha")


@respx.mock
def test_download_fnm_multi_platform_and_checksum(tmp_path: Path):
    import hashlib

    arm64_data = b"arm64 fnm zip data"
    arm64_sha = hashlib.sha256(arm64_data).hexdigest()
    macos_data = b"macos fnm zip data"
    macos_sha = hashlib.sha256(macos_data).hexdigest()

    respx.get(FNM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v1.38.1",
                "assets": [
                    {
                        "name": "fnm-arm64.zip",
                        "browser_download_url": "https://download/fnm-arm64.zip",
                    },
                    {
                        "name": "fnm-macos.zip",
                        "browser_download_url": "https://download/fnm-macos.zip",
                    },
                ],
            },
        )
    )
    respx.get("https://download/fnm-arm64.zip").mock(
        return_value=httpx.Response(200, content=arm64_data)
    )
    respx.get("https://download/fnm-macos.zip").mock(
        return_value=httpx.Response(200, content=macos_data)
    )

    with httpx.Client() as client:
        # Success with expected sha
        result = download_fnm(
            client,
            tmp_path,
            platforms=["linux-arm64", "darwin-arm64"],
            expected_sha256={
                "fnm-arm64.zip": arm64_sha,
                "fnm-macos.zip": macos_sha,
            },
        )
        assert len(result["zip_filenames"]) == 2
        assert "fnm-arm64-v1.38.1.zip" in result["zip_filenames"]

        # Failure on mismatch
        with pytest.raises(ChecksumMismatchError, match="Checksum mismatch"):
            download_fnm(
                client,
                tmp_path,
                platforms=["linux-arm64"],
                expected_sha256={"fnm-arm64.zip": "wrong-sha"},
            )


@respx.mock
def test_download_fnm_missing_asset_warning(tmp_path: Path):
    respx.get(FNM_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v1.38.1",
                "assets": [],
            },
        )
    )

    with httpx.Client() as client:
        result = download_fnm(client, tmp_path, platforms=["darwin-arm64"])
        assert result["version"] == "v1.38.1"
        assert result["zip_filename"] == "fnm-linux-v1.38.1.zip"


def test_setup_fnm_script_contains_python_fallback(tmp_path: Path):
    fnm_info: FnmReleaseInfo = {
        "version": "v1.38.1",
        "zip_filename": "fnm-linux-v1.38.1.zip",
    }
    scripts = generate_setup_scripts(tmp_path, fnm_info=fnm_info)
    assert len(scripts) == 1
    content = scripts[0].read_text(encoding="utf-8")
    assert "command -v unzip" in content
    assert "python3 -m zipfile -e" in content
    assert "uname -s" in content
    assert "uname -m" in content


def test_is_retryable_tool_error():
    req = httpx.Request("GET", "https://example.com")
    resp_500 = httpx.Response(500, request=req)
    resp_404 = httpx.Response(404, request=req)

    assert (
        _is_retryable_tool_error(
            httpx.HTTPStatusError("server error", request=req, response=resp_500)
        )
        is True
    )
    assert (
        _is_retryable_tool_error(
            httpx.HTTPStatusError("not found", request=req, response=resp_404)
        )
        is False
    )
    assert _is_retryable_tool_error(ChecksumMismatchError("bad sha")) is False
    assert _is_retryable_tool_error(RuntimeError("network error")) is True
