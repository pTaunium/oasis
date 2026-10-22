"""Release Catalog module for node-oasis.

Encapsulates upstream Node.js distribution metadata fetching, LTS release
schedule evaluation, platform filtering, and index table generation behind a
cohesive, deep module seam.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import (
    NodeIndex,
    NodeRelease,
    ReleaseSchedule,
    ResolvedCatalog,
)
from .utils import normalize_platform

logger = logging.getLogger(__name__)

DEFAULT_NODEJS_DIST_URL = "https://nodejs.org/dist"
DEFAULT_SCHEDULE_URL = (
    "https://raw.githubusercontent.com/nodejs/Release/main/schedule.json"
)

_PLATFORM_TO_INDEX_FILE: dict[str, str] = {
    "darwin-arm64": "osx-arm64-tar",
    "darwin-x64": "osx-x64-tar",
    "win-x64": "win-x64-zip",
    "win-arm64": "win-arm64-zip",
    "win-x86": "win-x86-zip",
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_index_json(url: str, timeout: float = 30.0) -> NodeIndex:
    """Download and return index.json as a list of releases."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_index_tab(url: str, timeout: float = 30.0) -> str:
    """Download and return index.tab as raw text."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_schedule(url: str, timeout: float = 30.0) -> ReleaseSchedule:
    """Download and return schedule.json mapping version to schedule."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def _matches_platform(files: Sequence[str], canonical_platform: str) -> bool:
    """Check if a canonical platform identifier or its upstream index alias is present in files."""
    if canonical_platform in files:
        return True
    mapped_index_file = _PLATFORM_TO_INDEX_FILE.get(canonical_platform)
    return mapped_index_file is not None and mapped_index_file in files


def _parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a version string like 'v22.14.0' to (22, 14, 0)."""
    if not version_str:
        return (0, 0, 0)
    clean_version = version_str[1:] if version_str[0] in "vV" else version_str
    parts = clean_version.split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 and parts[0] else 0
        minor = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        patch = int(parts[2]) if len(parts) > 2 and parts[2] else 0
    except ValueError:
        return (0, 0, 0)
    return (major, minor, patch)


def _get_active_lts_majors(
    schedule: ReleaseSchedule,
    *,
    today: datetime.date | None = None,
) -> list[int]:
    """Return major version numbers that are currently Active LTS or Maintenance LTS."""
    majors: list[int] = []
    current_date = (today if today is not None else datetime.date.today()).isoformat()
    for version_key, entry in schedule.items():
        if not version_key.startswith("v"):
            continue
        try:
            major = int(version_key[1:])
        except ValueError:
            continue

        lts_date = entry.get("lts")
        if not lts_date or not isinstance(lts_date, str) or lts_date > current_date:
            continue

        end_date = entry.get("end")
        if end_date and end_date >= current_date:
            majors.append(major)
    return majors


def _keep_latest_per_major(releases: NodeIndex) -> NodeIndex:
    """For each major version, keep only the one with the highest (major, minor, patch)."""
    latest_per_major: dict[int, tuple[tuple[int, int, int], NodeRelease]] = {}

    for release in releases:
        version_str = release.get("version", "")
        if not version_str:
            continue
        version_tuple = _parse_version(version_str)
        major = version_tuple[0]

        if major not in latest_per_major or version_tuple > latest_per_major[major][0]:
            latest_per_major[major] = (version_tuple, release)

    sorted_majors = sorted(latest_per_major.keys(), reverse=True)
    return [latest_per_major[major][1] for major in sorted_majors]


def _partition_version_targets(
    versions: Sequence[str | int],
) -> tuple[set[str], set[int]]:
    """Partition requested version specs into exact version strings and major version integers."""
    exact_versions: set[str] = set()
    major_versions: set[int] = set()

    for version_spec in versions:
        version_str = str(version_spec).strip()
        if not version_str:
            continue
        clean_version = version_str[1:] if version_str[0] in "vV" else version_str
        if "." in clean_version:
            exact_versions.add("v" + clean_version)
        else:
            try:
                major_versions.add(int(clean_version))
            except ValueError:
                continue

    return exact_versions, major_versions


def _filter_releases(
    releases: NodeIndex,
    versions: Sequence[str | int] | None = None,
    platforms: Sequence[str] | None = None,
) -> NodeIndex:
    """Filter releases by platform availability and versions, keeping latest patch per major for major targets."""
    # 1. Filter by platform availability first so latest patch selection considers only supported releases
    if platforms is not None:
        canonical_platforms = [normalize_platform(p) for p in platforms]
        candidate_releases = [
            release
            for release in releases
            if any(
                _matches_platform(release.get("files") or [], platform)
                for platform in canonical_platforms
            )
        ]
    else:
        candidate_releases = releases

    if versions is None:
        return _keep_latest_per_major(candidate_releases)

    # 2. Separate exact version requests from major version requests
    exact_versions, major_versions = _partition_version_targets(versions)

    # 3. Collect exact matches and latest-per-major matches
    matched_by_version: dict[str, NodeRelease] = {}

    for release in candidate_releases:
        version = release.get("version", "")
        if version and version in exact_versions:
            matched_by_version[version] = release

    major_candidates = [
        release
        for release in candidate_releases
        if _parse_version(release.get("version", ""))[0] in major_versions
    ]
    for release in _keep_latest_per_major(major_candidates):
        version = release.get("version", "")
        if version:
            matched_by_version[version] = release

    return sorted(
        matched_by_version.values(),
        key=lambda r: _parse_version(r.get("version", "")),
        reverse=True,
    )


def _filter_index_tab(raw_tab: str, versions: set[str]) -> str:
    """Filter index.tab lines to only include versions in the set, preserving the header."""
    lines = raw_tab.splitlines()
    if not lines:
        return ""

    filtered = [lines[0]]  # Header line
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts[0] in versions:
            filtered.append(line)

    return "\n".join(filtered) + "\n"


def resolve_catalog(
    versions: Sequence[str | int] | None = None,
    platforms: Sequence[str] | None = None,
    *,
    latest_lts: bool = False,
    nodejs_dist_url: str = DEFAULT_NODEJS_DIST_URL,
    schedule_url: str = DEFAULT_SCHEDULE_URL,
    timeout: float = 30.0,
    today: datetime.date | None = None,
) -> ResolvedCatalog:
    """Resolve target Node.js releases and index metadata from upstream distributions.

    Fetches upstream index.json, index.tab, and schedule.json, evaluates active
    LTS milestones, filters matching releases across requested platforms, keeps
    the latest patch per major, and produces a synchronized index.tab content.
    """
    clean_dist_url = nodejs_dist_url.rstrip("/")

    logger.info("Fetching upstream catalog metadata...")
    index_json = _fetch_index_json(f"{clean_dist_url}/index.json", timeout=timeout)
    index_tab_raw = _fetch_index_tab(f"{clean_dist_url}/index.tab", timeout=timeout)

    target_versions: list[str] = [str(v) for v in versions] if versions else []

    if latest_lts:
        schedule = _fetch_schedule(schedule_url, timeout=timeout)
        active_majors = _get_active_lts_majors(schedule, today=today)
        target_versions.extend(str(major) for major in active_majors)

    filtered_releases = _filter_releases(
        index_json,
        versions=target_versions if (versions is not None or latest_lts) else None,
        platforms=platforms,
    )

    filtered_version_set = {
        release["version"] for release in filtered_releases if release.get("version")
    }
    filtered_tab = _filter_index_tab(index_tab_raw, filtered_version_set)

    logger.info(
        "Resolved catalog with %d releases for platforms %s",
        len(filtered_releases),
        list(platforms) if platforms else "all",
    )

    return {
        "releases": filtered_releases,
        "index_tab_content": filtered_tab,
        "target_versions": target_versions,
    }
