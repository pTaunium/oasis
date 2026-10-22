"""Download and setup scripts for NVM and fnm."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .models import (
    ChecksumMismatchError,
    FnmReleaseInfo,
    NvmReleaseInfo,
)
from .utils import calculate_sha256, normalize_platform

logger = logging.getLogger(__name__)

BASE_URL_PLACEHOLDER = "{{BASE_URL}}"
NVM_API_URL = "https://api.github.com/repos/nvm-sh/nvm/releases/latest"
FNM_API_URL = "https://api.github.com/repos/Schniz/fnm/releases/latest"

_calculate_sha256 = calculate_sha256


def _get_github_headers() -> dict[str, str]:
    """Return authorization headers if GITHUB_TOKEN or GH_TOKEN is available."""
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _is_retryable_tool_error(exc: BaseException) -> bool:
    """Determine if an exception should be retried during tool downloads.

    Note: ChecksumMismatchError is intentionally not retried here because tool
    checksums are configured statically via config.toml. If an expected checksum
    fails to match the upstream asset, re-downloading the same release will not
    resolve a misconfigured expectation.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return not isinstance(exc, ChecksumMismatchError)


def get_fnm_asset_name_for_platform(platform: str) -> str:
    """Map Node.js platform identifier to fnm release asset name."""
    normalized = normalize_platform(platform)
    if normalized.startswith(("linux-arm64", "linux-aarch64")):
        return "fnm-arm64.zip"
    if normalized.startswith("linux-arm"):
        return "fnm-arm32.zip"
    if normalized.startswith("linux-"):
        return "fnm-linux.zip"
    if normalized.startswith("darwin-"):
        return "fnm-macos.zip"
    if normalized.startswith("win-"):
        return "fnm-windows.zip"
    return "fnm-linux.zip"


@retry(
    retry=retry_if_exception(_is_retryable_tool_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _get_latest_release_info(client: httpx.Client, api_url: str) -> dict[str, str]:
    """Query GitHub API for latest NVM release info."""
    headers = _get_github_headers()
    response = client.get(api_url, headers=headers, follow_redirects=True)
    response.raise_for_status()
    data = response.json()

    version = str(data.get("tag_name", ""))
    return {"version": version, "download_url": str(data.get("tarball_url", ""))}


@retry(
    retry=retry_if_exception(_is_retryable_tool_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def download_nvm(
    client: httpx.Client,
    output_dir: Path,
    *,
    api_url: str = NVM_API_URL,
    expected_sha256: str | None = None,
) -> NvmReleaseInfo:
    """Download NVM install.sh and source tarball with SHA-256 verification."""
    info = _get_latest_release_info(client, api_url)
    version = info["version"]

    nvm_dir = output_dir / "nvm"
    nvm_dir.mkdir(parents=True, exist_ok=True)

    # Download install.sh
    install_url = f"https://raw.githubusercontent.com/nvm-sh/nvm/{version}/install.sh"
    response = client.get(install_url, follow_redirects=True)
    response.raise_for_status()
    install_path = nvm_dir / "install.sh"
    with install_path.open("wb") as f:
        f.write(response.content)
    logger.info(
        "Downloaded NVM install.sh (SHA-256: %s)", _calculate_sha256(install_path)
    )

    # Download tarball
    tarball_url = info["download_url"]
    tarball_filename = f"nvm-{version}.tar.gz"
    tarball_path = nvm_dir / tarball_filename

    response = client.get(tarball_url, follow_redirects=True)
    response.raise_for_status()
    with tarball_path.open("wb") as f:
        f.write(response.content)

    actual_sha = _calculate_sha256(tarball_path)
    logger.info("Downloaded %s (SHA-256: %s)", tarball_filename, actual_sha)

    if expected_sha256 and actual_sha != expected_sha256:
        tarball_path.unlink(missing_ok=True)
        raise ChecksumMismatchError(
            f"Checksum mismatch for {tarball_filename}: expected {expected_sha256}, got {actual_sha}"
        )

    return {"version": version, "tarball_filename": tarball_filename}


@retry(
    retry=retry_if_exception(_is_retryable_tool_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def download_fnm(
    client: httpx.Client,
    output_dir: Path,
    *,
    api_url: str = FNM_API_URL,
    platforms: Sequence[str] | None = None,
    expected_sha256: dict[str, str] | None = None,
) -> FnmReleaseInfo:
    """Download fnm release zip assets with multi-platform mapping and SHA-256 verification."""
    headers = _get_github_headers()
    response = client.get(api_url, headers=headers, follow_redirects=True)
    response.raise_for_status()
    data = response.json()

    version = data.get("tag_name", "")
    assets = data.get("assets", [])

    # Map available assets: name -> download URL
    asset_urls: dict[str, str] = {
        a["name"]: a["browser_download_url"]
        for a in assets
        if "name" in a and "browser_download_url" in a
    }

    target_platforms = [normalize_platform(p) for p in (platforms or ["linux-x64"])]
    needed_asset_names = {get_fnm_asset_name_for_platform(p) for p in target_platforms}

    fnm_dir = output_dir / "fnm"
    fnm_dir.mkdir(parents=True, exist_ok=True)

    downloaded_zips: list[str] = []
    primary_zip: str | None = None

    for asset_name in sorted(needed_asset_names):
        url = asset_urls.get(asset_name)
        if not url:
            logger.warning(
                "fnm asset %s not available in release %s", asset_name, version
            )
            continue

        base_name = asset_name.removesuffix(".zip")
        zip_filename = f"{base_name}-{version}.zip"
        dest_path = fnm_dir / zip_filename

        download_response = client.get(url, follow_redirects=True)
        download_response.raise_for_status()
        with dest_path.open("wb") as f:
            f.write(download_response.content)

        actual_sha = _calculate_sha256(dest_path)
        logger.info("Downloaded %s (SHA-256: %s)", zip_filename, actual_sha)

        if expected_sha256:
            expected_sha = expected_sha256.get(asset_name) or expected_sha256.get(
                zip_filename
            )
            if expected_sha and actual_sha != expected_sha:
                dest_path.unlink(missing_ok=True)
                raise ChecksumMismatchError(
                    f"Checksum mismatch for {zip_filename}: expected {expected_sha}, got {actual_sha}"
                )

        downloaded_zips.append(zip_filename)
        if primary_zip is None or "linux" in zip_filename:
            primary_zip = zip_filename

    if primary_zip is None:
        primary_zip = f"fnm-linux-{version}.zip"

    return {
        "version": version,
        "zip_filename": primary_zip,
        "zip_filenames": downloaded_zips,
    }


def generate_setup_scripts(
    output_dir: Path,
    *,
    nvm_info: NvmReleaseInfo | None = None,
    fnm_info: FnmReleaseInfo | None = None,
) -> list[Path]:
    """Generate setup-nvm.sh.template and/or setup-fnm.sh.template."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scripts = []

    if nvm_info:
        nvm_dir = output_dir / "nvm"
        nvm_dir.mkdir(parents=True, exist_ok=True)
        nvm_script = f"""#!/bin/bash
# setup-nvm.sh — Generated by node-oasis for air-gapped NVM installation
set -e

NVM_DIR="${{NVM_DIR:-$HOME/.nvm}}"
mkdir -p "$NVM_DIR"

TMP_TAR="$(mktemp "${{TMPDIR:-/tmp}}/nvm-airgap.XXXXXX")"
trap 'rm -f "$TMP_TAR"' EXIT
echo "Downloading NVM from mirror..."
curl -fsSL "{BASE_URL_PLACEHOLDER}/tools/nvm/{nvm_info["tarball_filename"]}" -o "$TMP_TAR"

echo "Extracting NVM into $NVM_DIR..."
tar -xzf "$TMP_TAR" -C "$NVM_DIR" --strip-components=1

# Detect shell profile and append initialization if not already present
PROFILE=""
if [ -n "$("${{SHELL:-sh}}" -c 'echo $ZSH_VERSION')" ] || [ -n "$ZSH_VERSION" ]; then
    PROFILE="$HOME/.zshrc"
elif [ -n "$("${{SHELL:-sh}}" -c 'echo $BASH_VERSION')" ] || [ -n "$BASH_VERSION" ]; then
    if [ -f "$HOME/.bashrc" ]; then
        PROFILE="$HOME/.bashrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        PROFILE="$HOME/.bash_profile"
    fi
fi
if [ -z "$PROFILE" ]; then
    PROFILE="$HOME/.profile"
fi

if [ ! -f "$PROFILE" ]; then
    touch "$PROFILE"
fi

if ! grep -qc 'NVM_DIR' "$PROFILE"; then
    echo "Appending NVM configuration to $PROFILE..."
    cat << 'EOF' >> "$PROFILE"

# NVM configuration (node-oasis)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \\. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \\. "$NVM_DIR/bash_completion"
EOF
fi
if ! grep -qc 'NVM_NODEJS_ORG_MIRROR' "$PROFILE"; then
    echo "export NVM_NODEJS_ORG_MIRROR=\"{BASE_URL_PLACEHOLDER}/dist\"" >> "$PROFILE"
fi

echo "NVM installed successfully to $NVM_DIR"
echo "Active mirror: {BASE_URL_PLACEHOLDER}/dist"
echo "To start using NVM now, run:"
echo "  export NVM_DIR=\"$NVM_DIR\""
echo "  [ -s \"$NVM_DIR/nvm.sh\" ] && \\. \"$NVM_DIR/nvm.sh\""
echo "  export NVM_NODEJS_ORG_MIRROR=\"{BASE_URL_PLACEHOLDER}/dist\""
"""
        nvm_path = nvm_dir / "setup-nvm.sh.template"
        with nvm_path.open("w", encoding="utf-8") as f:
            f.write(nvm_script)
        scripts.append(nvm_path)

    if fnm_info:
        fnm_dir = output_dir / "fnm"
        fnm_dir.mkdir(parents=True, exist_ok=True)
        fnm_script = f"""#!/bin/bash
# setup-fnm.sh — Generated by node-oasis
set -e
FNM_DIR="${{FNM_DIR:-$HOME/.local/share/fnm}}"
mkdir -p "$FNM_DIR"

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$OS" in
  linux)
    case "$ARCH" in
      x86_64|amd64) FNM_ARCH="linux" ;;
      aarch64|arm64) FNM_ARCH="arm64" ;;
      armv7l|armv6l) FNM_ARCH="arm32" ;;
      *) FNM_ARCH="linux" ;;
    esac
    ;;
  darwin)
    FNM_ARCH="macos"
    ;;
  cygwin*|mingw*|msys*)
    FNM_ARCH="windows"
    ;;
  *)
    FNM_ARCH="linux"
    ;;
esac

ZIP_FILE="fnm-${{FNM_ARCH}}-{fnm_info["version"]}.zip"
TMP_ZIP="$(mktemp "${{TMPDIR:-/tmp}}/fnm.XXXXXX")"
trap 'rm -f "$TMP_ZIP"' EXIT

if ! curl -fsSL "{BASE_URL_PLACEHOLDER}/tools/fnm/${{ZIP_FILE}}" -o "$TMP_ZIP" 2>/dev/null; then
    curl -fsSL "{BASE_URL_PLACEHOLDER}/tools/fnm/{fnm_info["zip_filename"]}" -o "$TMP_ZIP"
fi

if command -v unzip > /dev/null 2>&1; then
    unzip -o "$TMP_ZIP" -d "$FNM_DIR"
elif command -v python3 > /dev/null 2>&1; then
    python3 -m zipfile -e "$TMP_ZIP" "$FNM_DIR"
else
    echo "Error: neither unzip nor python3 found to extract fnm.zip" >&2
    exit 1
fi

[ -f "$FNM_DIR/fnm" ] && chmod +x "$FNM_DIR/fnm"
[ -f "$FNM_DIR/fnm.exe" ] && chmod +x "$FNM_DIR/fnm.exe"
echo "fnm installed to $FNM_DIR"
echo "Add to PATH: export PATH=\\"$FNM_DIR:\\$PATH\\""
echo "Set mirror:  export FNM_NODE_DIST_MIRROR=\\"{BASE_URL_PLACEHOLDER}/dist\\""
"""
        fnm_path = fnm_dir / "setup-fnm.sh.template"
        with fnm_path.open("w", encoding="utf-8") as f:
            f.write(fnm_script)
        scripts.append(fnm_path)

    return scripts


def download_tools(
    output_dir: Path,
    *,
    tools: list[str],
    platforms: Sequence[str] | None = None,
    nvm_api_url: str = NVM_API_URL,
    fnm_api_url: str = FNM_API_URL,
    nvm_sha256: str | None = None,
    fnm_sha256: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> None:
    """Download requested tools and generate wrapper scripts."""
    nvm_info = None
    fnm_info = None

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        if "nvm" in tools:
            logger.info("Downloading NVM...")
            nvm_info = download_nvm(
                client,
                output_dir,
                api_url=nvm_api_url,
                expected_sha256=nvm_sha256,
            )

        if "fnm" in tools:
            logger.info("Downloading fnm...")
            fnm_info = download_fnm(
                client,
                output_dir,
                api_url=fnm_api_url,
                platforms=platforms,
                expected_sha256=fnm_sha256,
            )

    generate_setup_scripts(output_dir, nvm_info=nvm_info, fnm_info=fnm_info)
