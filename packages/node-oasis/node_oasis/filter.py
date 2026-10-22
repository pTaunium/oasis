"""Filter Node.js releases."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from .models import NodeIndex, NodeRelease, ReleaseSchedule

PLATFORM_ALIASES: dict[str, str] = {
    "osx-arm64": "darwin-arm64",
    "osx-x64": "darwin-x64",
    "darwin-aarch64": "darwin-arm64",
    "linux-aarch64": "linux-arm64",
    "win-ia32": "win-x86",
    "win32": "win-x86",
    "windows-x64": "win-x64",
    "windows-arm64": "win-arm64",
    "windows-x86": "win-x86",
}


def normalize_platform(platform: str) -> str:
    """Normalize user/config platform alias to canonical upstream archive platform name."""
    clean = platform.strip().lower()
    return PLATFORM_ALIASES.get(clean, clean)


PLATFORM_TO_INDEX_FILE: dict[str, str] = {
    "darwin-arm64": "osx-arm64-tar",
    "darwin-x64": "osx-x64-tar",
    "win-x64": "win-x64-zip",
    "win-arm64": "win-arm64-zip",
    "win-x86": "win-x86-zip",
}


def _matches_platform(files: Sequence[str], platform: str) -> bool:
    """Check if a platform identifier or its upstream index alias is present in files."""
    canonical = normalize_platform(platform)
    if canonical in files:
        return True
    mapped = PLATFORM_TO_INDEX_FILE.get(canonical)
    return mapped is not None and mapped in files


def _parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a version string like 'v22.14.0' to (22, 14, 0)."""
    if not version_str:
        return (0, 0, 0)
    version_str = version_str[1:] if version_str[0] in "vV" else version_str
    parts = version_str.split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 and parts[0] else 0
        minor = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        patch = int(parts[2]) if len(parts) > 2 and parts[2] else 0
    except ValueError:
        return (0, 0, 0)
    return (major, minor, patch)


def get_active_lts_majors(
    schedule: ReleaseSchedule,
    *,
    today: datetime.date | None = None,
) -> list[int]:
    """Return major version numbers that are currently Active LTS or Maintenance LTS."""
    majors = []
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

    return [item[1] for item in latest_per_major.values()]


def _parse_target_versions(
    versions: Sequence[str | int] | None, majors: Sequence[int] | None
) -> tuple[set[int], set[str]]:
    """Parse versions and majors into target major numbers and exact version strings."""
    target_majors: set[int] = set(majors or [])
    target_exact_versions: set[str] = set()

    if versions:
        for version_item in versions:
            v_str = str(version_item).strip()
            if not v_str:
                continue
            clean_version = v_str[1:] if v_str[0] in "vV" else v_str
            if "." in clean_version:
                target_exact_versions.add(f"v{clean_version}")
            else:
                try:
                    target_majors.add(int(clean_version))
                except ValueError:
                    continue
    return target_majors, target_exact_versions


def filter_releases(
    index: NodeIndex,
    *,
    versions: Sequence[str | int] | None = None,
    majors: Sequence[int] | None = None,
    platform: str | None = None,
    platforms: Sequence[str] | None = None,
) -> NodeIndex:
    """Filter to requested versions/majors and platforms, sorted descending."""
    target_platforms = [
        normalize_platform(p)
        for p in (
            list(platforms)
            if platforms is not None
            else ([platform] if platform is not None else ["linux-x64"])
        )
    ]

    target_majors, target_exact_versions = _parse_target_versions(versions, majors)

    platform_matched_releases: list[NodeRelease] = []
    for release in index:
        files = release.get("files", [])
        if any(_matches_platform(files, p) for p in target_platforms):
            platform_matched_releases.append(release)

    exact_matches: list[NodeRelease] = []
    major_candidates: list[NodeRelease] = []

    for release in platform_matched_releases:
        version_str = release.get("version", "")
        if version_str in target_exact_versions:
            exact_matches.append(release)

        major, _, _ = _parse_version(version_str)
        if major in target_majors:
            major_candidates.append(release)

    latest_per_major = _keep_latest_per_major(major_candidates)

    seen_versions: set[str] = set()
    combined: list[NodeRelease] = []
    for release in exact_matches + latest_per_major:
        version_str = release.get("version", "")
        if version_str and version_str not in seen_versions:
            seen_versions.add(version_str)
            combined.append(release)

    # Sort descending by parsed version
    combined.sort(
        key=lambda release: _parse_version(release.get("version", "")), reverse=True
    )
    return combined
