from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import respx
from node_oasis.downloader import (
    ChecksumMismatchError,
    _calculate_sha256,
    _get_expected_checksum,
    download_file,
    download_node_releases,
    get_archive_extensions,
)
from node_oasis.models import NodeIndex


def test_calculate_sha256(tmp_path: Path):
    f = tmp_path / "sample.txt"
    f.write_bytes(b"hello node-oasis")
    expected = hashlib.sha256(b"hello node-oasis").hexdigest()
    assert _calculate_sha256(f) == expected


def test_get_expected_checksum_success(tmp_path: Path):
    shasums = tmp_path / "SHASUMS256.txt"
    shasums.write_text("abcdef1234  node-v22.14.0-linux-x64.tar.xz\n", encoding="utf-8")
    assert (
        _get_expected_checksum("node-v22.14.0-linux-x64.tar.xz", shasums)
        == "abcdef1234"
    )


def test_get_expected_checksum_binary_mode(tmp_path: Path):
    shasums = tmp_path / "SHASUMS256.txt"
    shasums.write_text("abcdef1234 *node-v22.14.0-linux-x64.tar.xz\n", encoding="utf-8")
    assert (
        _get_expected_checksum("node-v22.14.0-linux-x64.tar.xz", shasums)
        == "abcdef1234"
    )


def test_get_expected_checksum_missing(tmp_path: Path):
    shasums = tmp_path / "SHASUMS256.txt"
    shasums.write_text("abcdef1234  other-file.tar.xz\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"Checksum for .* not found"):
        _get_expected_checksum("node-v22.14.0-linux-x64.tar.xz", shasums)


def test_get_expected_checksum_exact_match_only(tmp_path: Path):
    shasums = tmp_path / "SHASUMS256.txt"
    shasums.write_text(
        "0000000000000000000000000000000000000000000000000000000000000000  prefix-node-v22.14.0-linux-x64.tar.xz\n"
        "correctsha  node-v22.14.0-linux-x64.tar.xz\n",
        encoding="utf-8",
    )
    assert (
        _get_expected_checksum("node-v22.14.0-linux-x64.tar.xz", shasums)
        == "correctsha"
    )


@respx.mock
def test_download_file_new_and_skip(tmp_path: Path):
    dest = tmp_path / "download.tar.xz"
    url = "https://nodejs.org/dist/sample.tar.xz"
    respx.get(url).mock(return_value=httpx.Response(200, content=b"chunk data"))

    with httpx.Client() as client:
        # First download
        download_file(client, url, dest)
        assert dest.exists()
        assert dest.read_bytes() == b"chunk data"

        # Calling again should skip without error
        download_file(client, url, dest)


@respx.mock
def test_download_file_cleans_up_on_failure(tmp_path: Path):
    dest = tmp_path / "failed.tar.xz"
    url = "https://nodejs.org/dist/failed.tar.xz"
    respx.get(url).mock(return_value=httpx.Response(500))

    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        download_file(client, url, dest)

    assert not dest.exists()


@respx.mock
def test_download_node_releases(tmp_path: Path):
    releases: NodeIndex = [
        {"version": "v22.14.0", "files": ["linux-x64"]},
        {"version": ""},  # Should skip empty version
    ]
    dist_url = "https://nodejs.org/dist"

    tarball_data = b"tarball binary data"
    tarball_sha = hashlib.sha256(tarball_data).hexdigest()
    shasums_data = f"{tarball_sha}  node-v22.14.0-linux-x64.tar.xz\n".encode()
    asc_data = b"-----BEGIN PGP SIGNATURE-----\n..."

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(200, content=asc_data)
    )
    respx.get(f"{dist_url}/v22.14.0/node-v22.14.0-linux-x64.tar.xz").mock(
        return_value=httpx.Response(200, content=tarball_data)
    )

    downloaded = download_node_releases(releases, tmp_path, dist_url=dist_url)

    assert len(downloaded) == 1
    assert downloaded[0].name == "node-v22.14.0-linux-x64.tar.xz"
    assert downloaded[0].exists()
    assert (tmp_path / "v22.14.0" / "SHASUMS256.txt").exists()
    assert (tmp_path / "v22.14.0" / "SHASUMS256.txt.asc").exists()


@respx.mock
def test_download_node_releases_checksum_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["linux-x64"]}]
    dist_url = "https://nodejs.org/dist"

    monkeypatch.setattr("node_oasis.downloader.download_file.retry.sleep", Mock())

    tampered_data = b"tampered content"
    expected_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    shasums_data = f"{expected_sha}  node-v22.14.0-linux-x64.tar.xz\n".encode()

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(200, content=b"")
    )
    respx.get(f"{dist_url}/v22.14.0/node-v22.14.0-linux-x64.tar.xz").mock(
        return_value=httpx.Response(200, content=tampered_data)
    )

    with pytest.raises(ChecksumMismatchError):
        download_node_releases(releases, tmp_path, dist_url=dist_url)


@respx.mock
def test_download_file_replaces_corrupted_existing_file(tmp_path: Path):
    dest = tmp_path / "node-v22.14.0-linux-x64.tar.xz"
    dest.write_bytes(b"corrupted old file")

    url = "https://nodejs.org/dist/node-v22.14.0-linux-x64.tar.xz"
    fresh_content = b"fresh clean content"
    fresh_sha = hashlib.sha256(fresh_content).hexdigest()

    respx.get(url).mock(return_value=httpx.Response(200, content=fresh_content))

    with httpx.Client() as client:
        # dest exists with wrong checksum -> re-downloads and verifies
        download_file(client, url, dest, expected_sha256=fresh_sha)

    assert dest.read_bytes() == fresh_content


def test_download_file_skip_with_valid_checksum(tmp_path: Path):
    dest = tmp_path / "valid.tar.xz"
    content = b"already valid content"
    dest.write_bytes(content)
    valid_sha = hashlib.sha256(content).hexdigest()

    client = httpx.Client()
    # No HTTP route mocked; if it tries to fetch, it will fail
    result = download_file(
        client, "https://example.com/valid.tar.xz", dest, expected_sha256=valid_sha
    )

    assert result == dest
    assert dest.read_bytes() == content


def test_get_archive_extensions():
    assert get_archive_extensions("win-x64") == [".zip"]
    assert get_archive_extensions("win-arm64") == [".zip"]
    assert get_archive_extensions("linux-x64") == [".tar.xz", ".tar.gz"]
    assert get_archive_extensions("darwin-arm64") == [".tar.xz", ".tar.gz"]


@respx.mock
def test_download_file_retry_on_checksum_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("node_oasis.downloader.download_file.retry.sleep", Mock())
    dest = tmp_path / "retry-test.tar.xz"
    url = "https://nodejs.org/dist/retry-test.tar.xz"

    valid_content = b"good data after retry"
    valid_sha = hashlib.sha256(valid_content).hexdigest()

    # First attempt: corrupt content; second attempt: valid content
    route = respx.get(url)
    route.side_effect = [
        httpx.Response(200, content=b"corrupted first try"),
        httpx.Response(200, content=valid_content),
    ]

    with httpx.Client() as client:
        result = download_file(client, url, dest, expected_sha256=valid_sha)

    assert result == dest
    assert dest.read_bytes() == valid_content
    assert route.call_count == 2


@respx.mock
def test_download_node_releases_multiple_extensions(tmp_path: Path):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["linux-x64"]}]
    base_url = "https://nodejs.org/dist"
    dist_url_with_trailing_slash = f"{base_url}/"

    xz_data = b"xz tarball data"
    xz_sha = hashlib.sha256(xz_data).hexdigest()
    gz_data = b"gz tarball data"
    gz_sha = hashlib.sha256(gz_data).hexdigest()

    shasums_data = (
        f"{xz_sha}  node-v22.14.0-linux-x64.tar.xz\n"
        f"{gz_sha}  node-v22.14.0-linux-x64.tar.gz\n"
    ).encode()

    respx.get(f"{base_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    respx.get(f"{base_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(200, content=b"")
    )
    respx.get(f"{base_url}/v22.14.0/node-v22.14.0-linux-x64.tar.xz").mock(
        return_value=httpx.Response(200, content=xz_data)
    )
    respx.get(f"{base_url}/v22.14.0/node-v22.14.0-linux-x64.tar.gz").mock(
        return_value=httpx.Response(200, content=gz_data)
    )

    downloaded = download_node_releases(
        releases, tmp_path, platform="linux-x64", dist_url=dist_url_with_trailing_slash
    )

    assert len(downloaded) == 2
    filenames = {p.name for p in downloaded}
    assert filenames == {
        "node-v22.14.0-linux-x64.tar.xz",
        "node-v22.14.0-linux-x64.tar.gz",
    }


@respx.mock
def test_download_node_releases_windows_zip(tmp_path: Path):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["win-x64"]}]
    dist_url = "https://nodejs.org/dist"

    zip_data = b"windows zip binary data"
    zip_sha = hashlib.sha256(zip_data).hexdigest()

    shasums_data = f"{zip_sha}  node-v22.14.0-win-x64.zip\n".encode()

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(200, content=b"")
    )
    respx.get(f"{dist_url}/v22.14.0/node-v22.14.0-win-x64.zip").mock(
        return_value=httpx.Response(200, content=zip_data)
    )

    downloaded = download_node_releases(
        releases, tmp_path, platform="win-x64", dist_url=dist_url
    )

    assert len(downloaded) == 1
    assert downloaded[0].name == "node-v22.14.0-win-x64.zip"


@respx.mock
def test_download_node_releases_no_matching_archives(tmp_path: Path):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["linux-x64"]}]
    dist_url = "https://nodejs.org/dist"

    # SHASUMS contains only other platform
    shasums_data = b"0000000000000000000000000000000000000000000000000000000000000000  node-v22.14.0-osx-arm64.tar.gz\n"

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(200, content=b"")
    )

    with pytest.raises(ValueError, match="No matching archives found"):
        download_node_releases(
            releases, tmp_path, platform="linux-x64", dist_url=dist_url
        )


@respx.mock
def test_download_node_releases_asc_404_and_multi_platforms(tmp_path: Path):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["linux-x64", "win-x64"]}]
    dist_url = "https://nodejs.org/dist"

    xz_data = b"xz tarball data"
    xz_sha = hashlib.sha256(xz_data).hexdigest()
    zip_data = b"zip binary data"
    zip_sha = hashlib.sha256(zip_data).hexdigest()

    shasums_data = (
        f"{xz_sha}  node-v22.14.0-linux-x64.tar.xz\n"
        f"{zip_sha}  node-v22.14.0-win-x64.zip\n"
    ).encode()

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    # 404 on asc file
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{dist_url}/v22.14.0/node-v22.14.0-linux-x64.tar.xz").mock(
        return_value=httpx.Response(200, content=xz_data)
    )
    respx.get(f"{dist_url}/v22.14.0/node-v22.14.0-win-x64.zip").mock(
        return_value=httpx.Response(200, content=zip_data)
    )

    downloaded = download_node_releases(
        releases, tmp_path, platforms=["linux-x64", "win-x64"], dist_url=dist_url
    )
    assert len(downloaded) == 2


@respx.mock
def test_download_node_releases_asc_500_raises(tmp_path: Path):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["linux-x64"]}]
    dist_url = "https://nodejs.org/dist"

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=b"")
    )
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(500)
    )

    with pytest.raises(httpx.HTTPStatusError):
        download_node_releases(
            releases, tmp_path, platform="linux-x64", dist_url=dist_url
        )


@respx.mock
def test_download_node_releases_with_platform_alias(tmp_path: Path):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["osx-arm64-tar"]}]
    dist_url = "https://nodejs.org/dist"

    tar_data = b"darwin arm64 tarball"
    tar_sha = hashlib.sha256(tar_data).hexdigest()
    shasums_data = f"{tar_sha}  node-v22.14.0-darwin-arm64.tar.gz\n".encode()

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{dist_url}/v22.14.0/node-v22.14.0-darwin-arm64.tar.gz").mock(
        return_value=httpx.Response(200, content=tar_data)
    )

    # Use alias 'osx-arm64', should normalize to 'darwin-arm64'
    downloaded = download_node_releases(
        releases, tmp_path, platforms=["osx-arm64"], dist_url=dist_url
    )
    assert len(downloaded) == 1
    assert downloaded[0].name == "node-v22.14.0-darwin-arm64.tar.gz"


@respx.mock
def test_download_node_releases_partial_platform_missing_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    releases: NodeIndex = [{"version": "v22.14.0", "files": ["linux-x64"]}]
    dist_url = "https://nodejs.org/dist"

    tar_data = b"linux x64 tarball"
    tar_sha = hashlib.sha256(tar_data).hexdigest()
    # darwin-arm64 is NOT in SHASUMS256.txt
    shasums_data = f"{tar_sha}  node-v22.14.0-linux-x64.tar.xz\n".encode()

    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt").mock(
        return_value=httpx.Response(200, content=shasums_data)
    )
    respx.get(f"{dist_url}/v22.14.0/SHASUMS256.txt.asc").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{dist_url}/v22.14.0/node-v22.14.0-linux-x64.tar.xz").mock(
        return_value=httpx.Response(200, content=tar_data)
    )

    caplog.set_level(logging.WARNING)
    downloaded = download_node_releases(
        releases, tmp_path, platforms=["linux-x64", "darwin-arm64"], dist_url=dist_url
    )
    assert len(downloaded) == 1
    assert (
        "No matching archives found for v22.14.0 on platform 'darwin-arm64'"
        in caplog.text
    )
