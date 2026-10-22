"""Download and verify Node.js tarballs and SHASUMS files."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .models import ChecksumMismatchError, NodeIndex
from .utils import calculate_sha256, normalize_platform

logger = logging.getLogger(__name__)

_calculate_sha256 = calculate_sha256


def _get_expected_checksum(tarball_filename: str, shasums_path: Path) -> str:
    """Retrieve expected sha256 for tarball_filename from SHASUMS256.txt."""
    with shasums_path.open("r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                filename_entry = parts[1].strip().lstrip("*")
                if filename_entry == tarball_filename:
                    return parts[0]
    raise ValueError(
        f"Checksum for {tarball_filename} not found in {shasums_path.name}"
    )


def _is_retryable_download_error(exc: BaseException) -> bool:
    """Determine if an exception should be retried during release downloads.

    Transient HTTP server errors (>= 500), network errors, and ChecksumMismatchError
    (to recover from in-transit bit corruption or truncated streams) are retried.
    Non-transient HTTP client errors (4xx, such as 404 Not Found) are not retried.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return True


@retry(
    retry=retry_if_exception(_is_retryable_download_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def download_file(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    expected_sha256: str | None = None,
) -> Path:
    """Download a file streaming with 1MB chunks. Skip if exists and checksum matches."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and "SHASUMS256.txt" not in dest.name:
        if expected_sha256:
            actual_sha = _calculate_sha256(dest)
            if actual_sha == expected_sha256:
                logger.debug(
                    "File %s already exists with valid checksum, skipping.", dest
                )
                return dest
            logger.warning(
                "File %s exists but checksum mismatch (%s != %s). Re-downloading.",
                dest.name,
                actual_sha,
                expected_sha256,
            )
            dest.unlink(missing_ok=True)
        else:
            logger.debug("File %s already exists, skipping.", dest)
            return dest

    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    # Post-download verification (inside @retry boundary)
    if expected_sha256:
        actual_sha = _calculate_sha256(dest)
        if actual_sha != expected_sha256:
            dest.unlink(missing_ok=True)
            raise ChecksumMismatchError(
                f"Checksum mismatch for {dest.name}: "
                f"expected {expected_sha256}, got {actual_sha}"
            )

    return dest


def get_archive_extensions(platform: str) -> list[str]:
    """Return archive extensions to mirror for the given platform.

    Windows targets distribute .zip files.
    Linux/macOS and other Unix targets distribute .tar.xz and .tar.gz archives.
    Both .tar.xz and .tar.gz are supported so NVM clients lacking xz support
    can fall back to .tar.gz.
    """
    if platform.startswith("win-"):
        return [".zip"]
    return [".tar.xz", ".tar.gz"]


def download_node_releases(
    releases: NodeIndex,
    output_dir: Path,
    *,
    platform: str | None = None,
    platforms: Sequence[str] | None = None,
    dist_url: str = "https://nodejs.org/dist",
    timeout: float = 300.0,
) -> list[Path]:
    """Download tarballs/archives and checksums for the given releases across requested platforms."""
    downloaded = []
    dist_url = dist_url.rstrip("/")
    target_platforms = [
        normalize_platform(p)
        for p in (
            list(platforms)
            if platforms is not None
            else ([platform] if platform is not None else ["linux-x64"])
        )
    ]

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for idx, release in enumerate(releases, 1):
            version = release.get("version")
            if not version:
                continue

            logger.info("[%d/%d] %s", idx, len(releases), version)
            version_dir = output_dir / version
            version_dir.mkdir(parents=True, exist_ok=True)

            # Download SHASUMS256.txt
            shasums_url = f"{dist_url}/{version}/SHASUMS256.txt"
            shasums_path = version_dir / "SHASUMS256.txt"
            download_file(client, shasums_url, shasums_path)

            # Download SHASUMS256.txt.asc (optional if missing)
            shasums_asc_url = f"{dist_url}/{version}/SHASUMS256.txt.asc"
            shasums_asc_path = version_dir / "SHASUMS256.txt.asc"
            try:
                download_file(client, shasums_asc_url, shasums_asc_path)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.warning(
                        "SHASUMS256.txt.asc not found for %s, skipping", version
                    )
                else:
                    raise

            # Download Node archives for requested platforms
            found_platforms: set[str] = set()
            for target_platform in target_platforms:
                is_platform_found = False
                extensions = get_archive_extensions(target_platform)
                for ext in extensions:
                    archive_filename = f"node-{version}-{target_platform}{ext}"
                    try:
                        expected_sha = _get_expected_checksum(
                            archive_filename, shasums_path
                        )
                    except ValueError:
                        logger.debug(
                            "Archive %s not listed in %s, skipping",
                            archive_filename,
                            shasums_path.name,
                        )
                        continue

                    archive_url = f"{dist_url}/{version}/{archive_filename}"
                    archive_path = version_dir / archive_filename
                    download_file(
                        client, archive_url, archive_path, expected_sha256=expected_sha
                    )
                    downloaded.append(archive_path)
                    found_platforms.add(target_platform)
                    is_platform_found = True

                if not is_platform_found:
                    logger.warning(
                        "No matching archives found for %s on platform '%s' in %s",
                        version,
                        target_platform,
                        shasums_path.name,
                    )

            if not found_platforms:
                platforms_str = ", ".join(target_platforms)
                raise ValueError(
                    f"No matching archives found for {version} ({platforms_str}) in {shasums_path.name}"
                )

    return downloaded
