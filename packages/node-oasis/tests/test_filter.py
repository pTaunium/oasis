from __future__ import annotations

import datetime

from node_oasis.filter import (
    _keep_latest_per_major,
    _parse_version,
    filter_releases,
    get_active_lts_majors,
    normalize_platform,
)
from node_oasis.models import NodeIndex, ReleaseSchedule


def test_normalize_platform():
    assert normalize_platform("osx-arm64") == "darwin-arm64"
    assert normalize_platform("OSX-X64") == "darwin-x64"
    assert normalize_platform("win-ia32") == "win-x86"
    assert normalize_platform("linux-aarch64") == "linux-arm64"
    assert normalize_platform("linux-x64") == "linux-x64"


def test_parse_version():
    assert _parse_version("v22.14.0") == (22, 14, 0)
    assert _parse_version("V22.14.0") == (22, 14, 0)
    assert _parse_version("v20.0.1") == (20, 0, 1)
    assert _parse_version("18.19.0") == (18, 19, 0)
    assert _parse_version("") == (0, 0, 0)
    assert _parse_version("v10") == (10, 0, 0)
    assert _parse_version("invalid.version.number") == (0, 0, 0)


def test_get_active_lts_majors():
    static_today = datetime.date(2025, 6, 1)

    schedule: ReleaseSchedule = {
        "v24": {
            "start": "2024-04-23",
            "lts": "2024-10-29",
            "maintenance": "2025-10-28",
            "end": "2026-04-30",
            "codename": "Krypton",
        },
        "v22": {
            "start": "2024-04-23",
            "lts": "2024-10-29",
            "maintenance": "2025-10-21",
            "end": "2027-04-30",
            "codename": "Jod",
        },
        "v20": {
            "start": "2023-04-18",
            "lts": "2023-10-24",
            "maintenance": "2024-10-22",
            "end": "2025-04-30",  # EOL on 2025-06-01
            "codename": "Iron",
        },
        "v23": {
            # Not LTS
            "start": "2024-10-15",
            "end": "2025-06-01",
        },
        "v25": {
            # Odd release in maintenance window: has maintenance date passed, but no lts key
            "start": "2025-01-01",
            "maintenance": "2025-05-01",
            "end": "2026-01-01",
        },
        "invalid_key": {"end": "2026-01-01"},
        "vInvalid": {"end": "2026-01-01"},
    }

    # Test with explicit static date
    majors = get_active_lts_majors(schedule, today=static_today)
    assert 24 in majors
    assert 22 in majors
    assert 20 not in majors  # EOL
    assert 23 not in majors  # Non-LTS
    assert 25 not in majors  # Odd maintenance non-LTS release

    # Test with default today (None)
    default_majors = get_active_lts_majors(schedule)
    assert isinstance(default_majors, list)


def test_keep_latest_per_major():
    releases: NodeIndex = [
        {"version": "v22.14.0", "files": ["linux-x64"]},
        {"version": "v22.14.1", "files": ["linux-x64"]},
        {"version": "v22.13.0", "files": ["linux-x64"]},
        {"version": "v20.18.0", "files": ["linux-x64"]},
        {"version": "v20.18.1", "files": ["linux-x64"]},
        {"version": ""},  # empty version ignored
    ]

    latest = _keep_latest_per_major(releases)
    versions = {r.get("version") for r in latest}
    assert versions == {"v22.14.1", "v20.18.1"}


def test_filter_releases():
    releases: NodeIndex = [
        {"version": "v22.14.1", "files": ["linux-x64", "win-x64-zip"]},
        {"version": "v22.14.0", "files": ["linux-x64"]},
        {"version": "v20.18.1", "files": ["osx-arm64-tar"]},  # missing linux-x64
        {"version": "v20.18.0", "files": ["linux-x64"]},
        {"version": "v18.20.5", "files": ["linux-x64"]},
    ]

    # Target majors 22 and 20 for platform linux-x64
    result = filter_releases(releases, majors=[22, 20], platform="linux-x64")

    assert len(result) == 2
    assert result[0]["version"] == "v22.14.1"
    assert result[1]["version"] == "v20.18.0"


def test_filter_releases_custom_platform():
    releases: NodeIndex = [
        {"version": "v22.14.0", "files": ["linux-arm64"]},
        {"version": "v22.14.1", "files": ["linux-x64"]},
    ]

    result = filter_releases(releases, majors=[22], platform="linux-arm64")
    assert len(result) == 1
    assert result[0]["version"] == "v22.14.0"


def test_filter_releases_unified_versions_and_multi_platforms():
    releases: NodeIndex = [
        {"version": "v22.14.1", "files": ["linux-x64"]},
        {"version": "v22.14.0", "files": ["osx-arm64-tar"]},
        {"version": "v20.18.1", "files": ["linux-x64"]},
        {"version": "v20.11.1", "files": ["linux-x64"]},
        {"version": "v18.20.0", "files": ["win-x64-zip"]},
        {"version": ""},
    ]

    # Pass major 22 (string), exact 20.11.1 with uppercase V, invalid string, empty string
    result = filter_releases(
        releases,
        versions=["22", "V20.11.1", "", "invalid_version"],
        platforms=["linux-x64", "darwin-arm64"],
    )

    # 22 should pick latest among platforms -> v22.14.1
    # 20.11.1 should be exact matched -> v20.11.1
    assert len(result) == 2
    assert result[0]["version"] == "v22.14.1"
    assert result[1]["version"] == "v20.11.1"

    # darwin-arm64 matches upstream osx-arm64-tar
    darwin_result = filter_releases(
        releases,
        versions=["22"],
        platforms=["darwin-arm64"],
    )
    assert len(darwin_result) == 1
    assert darwin_result[0]["version"] == "v22.14.0"

    # win-x64 matches upstream win-x64-zip
    win_result = filter_releases(
        releases,
        versions=["18"],
        platforms=["win-x64"],
    )
    assert len(win_result) == 1
    assert win_result[0]["version"] == "v18.20.0"

    # osx-arm64 alias matches upstream osx-arm64-tar
    alias_result = filter_releases(
        releases,
        versions=["22"],
        platforms=["osx-arm64"],
    )
    assert len(alias_result) == 1
    assert alias_result[0]["version"] == "v22.14.0"
