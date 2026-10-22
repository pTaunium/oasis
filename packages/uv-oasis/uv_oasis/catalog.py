"""Release Catalog module for uv-oasis.

Encapsulates upstream Python standalone distribution metadata fetching,
variant filtering, platform matching, and latest patch deduplication behind a
cohesive, deep module seam.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import (
    FilterConfig,
    MetadataEntry,
    MetadataIndex,
    PlatformSpec,
    ResolvedCatalog,
)

logger = logging.getLogger(__name__)

# The canonical source for uv's Python download metadata.
DOWNLOAD_METADATA_URL = (
    "https://raw.githubusercontent.com/astral-sh/uv/main/"
    "crates/uv-python-managed/download-metadata.json"
)


class _ReleaseGroup(NamedTuple):
    """Identifies a unique grouping of Python releases for filtering."""

    minor: int
    variant: str | None
    os: str
    arch_family: str
    arch_variant: str | None
    libc: str | None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_metadata(
    url: str = DOWNLOAD_METADATA_URL, timeout: float = 30.0
) -> MetadataIndex:
    """Download and return the full download-metadata.json as a dict."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def _is_stable(entry: MetadataEntry) -> bool:
    """Return True if the entry is a stable release (no prerelease tag)."""
    return entry.get("prerelease", "") == ""


def _extract_version_tuple(entry: MetadataEntry) -> tuple[int, int, int]:
    """Extract (major, minor, patch) from an entry."""
    return (entry["major"], entry["minor"], entry["patch"])


def _get_candidate_entries(
    metadata: MetadataIndex,
    platforms: list[PlatformSpec],
    python_variants: set[str | None],
    cpu_variants: set[str | None],
) -> list[tuple[str, MetadataEntry]]:
    """Filter out entries that don't match the requested platforms and variants."""
    candidate_entries: list[tuple[str, MetadataEntry]] = []
    for dist_id, entry in metadata.items():
        if entry.get("name") != "cpython":
            continue
        if not _is_stable(entry):
            continue
        if entry.get("variant") not in python_variants:
            continue
        if not any(p.matches(entry, cpu_variants) for p in platforms):
            continue
        candidate_entries.append((dist_id, entry))
    return candidate_entries


def _keep_latest_patch(
    candidate_entries: list[tuple[str, MetadataEntry]],
) -> dict[_ReleaseGroup, tuple[str, MetadataEntry]]:
    """For each release group, keep only the one with the highest patch version."""
    latest_patch_entries_by_group: dict[_ReleaseGroup, tuple[str, MetadataEntry]] = {}
    for dist_id, entry in candidate_entries:
        group_key = _ReleaseGroup(
            minor=entry["minor"],
            variant=entry.get("variant"),
            os=entry["os"],
            arch_family=entry["arch"]["family"],
            arch_variant=entry["arch"].get("variant"),
            libc=entry.get("libc"),
        )
        existing_entry = latest_patch_entries_by_group.get(group_key)
        if not existing_entry or _extract_version_tuple(entry) > _extract_version_tuple(
            existing_entry[1]
        ):
            latest_patch_entries_by_group[group_key] = (dist_id, entry)
    return latest_patch_entries_by_group


def _sort_key(
    item: tuple[_ReleaseGroup, tuple[str, MetadataEntry]],
) -> tuple[int, int, int, str]:
    dist_id, entry = item[1]
    version_tuple = _extract_version_tuple(entry)
    return (-version_tuple[0], -version_tuple[1], -version_tuple[2], dist_id)


def _filter_entries(
    metadata: MetadataIndex,
    config: FilterConfig,
) -> MetadataIndex:
    """Filter the full metadata down to the entries we want to ship."""
    candidate_entries = _get_candidate_entries(
        metadata, config.platforms, config.python_variants, config.cpu_variants
    )
    latest_patch_entries_by_group = _keep_latest_patch(candidate_entries)
    sorted_items = sorted(latest_patch_entries_by_group.items(), key=_sort_key)
    return {dist_id: entry for _, (dist_id, entry) in sorted_items}


def resolve_catalog(
    config: FilterConfig,
    *,
    metadata_url: str | None = None,
    timeout: float = 30.0,
) -> ResolvedCatalog:
    """Resolve target Python standalone distributions from upstream metadata.

    Fetches download-metadata.json, filters candidates according to FilterConfig,
    keeps only the latest patch for each release group, and returns a ResolvedCatalog.
    """
    url = metadata_url or DOWNLOAD_METADATA_URL
    logger.info("Fetching upstream download-metadata.json...")
    metadata = _fetch_metadata(url=url, timeout=timeout)
    logger.info("Fetched %d total entries from metadata", len(metadata))

    entries = _filter_entries(metadata, config)
    logger.info("Filtered to %d entries", len(entries))

    return {"entries": entries}
