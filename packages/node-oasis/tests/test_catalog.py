from __future__ import annotations

import datetime

import httpx
import pytest
import respx
from node_oasis.catalog import (
    DEFAULT_NODEJS_DIST_URL,
    DEFAULT_SCHEDULE_URL,
    _filter_index_tab,
    _parse_version,
    resolve_catalog,
)
from node_oasis.models import (
    NodeIndex,
    ReleaseSchedule,
)
from node_oasis.utils import normalize_platform


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


def test_filter_index_tab_empty():
    assert _filter_index_tab("", {"v22.14.0"}) == ""


@respx.mock
def test_resolve_catalog_basic():
    mock_index: NodeIndex = [
        {"version": "v22.14.1", "files": ["linux-x64", "win-x64-zip"]},
        {"version": "v22.14.0", "files": ["linux-x64"]},
        {"version": "v20.18.1", "files": ["linux-x64"]},
        {"version": "v20.11.1", "files": ["linux-x64"]},
        {"version": "v18.20.0", "files": ["win-x64-zip"]},
        {"version": ""},
    ]
    raw_tab = (
        "version\tdate\tfpm\tnpm\tv8\tuv\tzlib\topenssl\tmodules\tlts\tsecurity\n"
        "v22.14.1\t2025-02-18\t\t10.9.2\t12.4.254.21\t1.49.2\t1.3.0.1\t3.0.15\t127\tJod\tfalse\n"
        "v20.11.1\t2024-02-14\t\t10.2.4\t11.3.244.8\t1.48.0\t1.3.0.1\t3.0.15\t115\tIron\tfalse\n"
        "v18.20.0\t2024-03-26\t\t10.5.0\t10.2.154.26\t1.44.2\t1.2.13.1\t3.0.13\t108\tHydrogen\tfalse\n"
    )

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )

    catalog = resolve_catalog(
        versions=["22", "V20.11.1", "", "invalid_version"],
        platforms=["linux-x64"],
    )

    releases = catalog["releases"]
    assert len(releases) == 2
    assert releases[0]["version"] == "v22.14.1"
    assert releases[1]["version"] == "v20.11.1"

    tab = catalog["index_tab_content"]
    assert "v22.14.1\t" in tab
    assert "v20.11.1\t" in tab
    assert "v18.20.0\t" not in tab


@respx.mock
def test_resolve_catalog_lts_and_platforms():
    mock_index: NodeIndex = [
        {"version": "v24.2.0", "files": ["linux-x64"]},
        {"version": "v22.14.0", "files": ["osx-arm64-tar", "linux-x64"]},
        {"version": "v20.18.1", "files": ["linux-x64"]},
        {"version": "v18.20.0", "files": ["win-x64-zip"]},
    ]
    raw_tab = "version\tdate\nv24.2.0\t2025-05-01\nv22.14.0\t2025-02-18\n"

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
        "v23": {"start": "2024-10-15", "end": "2025-06-01"},
        "v25": {
            "start": "2025-01-01",
            "maintenance": "2025-05-01",
            "end": "2026-01-01",
        },
        "invalid_key": {"end": "2026-01-01"},
        "vInvalid": {"end": "2026-01-01"},
    }

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )
    respx.get(DEFAULT_SCHEDULE_URL).mock(
        return_value=httpx.Response(200, json=schedule)
    )

    static_today = datetime.date(2025, 6, 1)
    catalog = resolve_catalog(
        platforms=["linux-x64"],
        latest_lts=True,
        today=static_today,
    )

    versions = [r["version"] for r in catalog["releases"]]
    assert versions == ["v24.2.0", "v22.14.0"]
    assert "24" in catalog["target_versions"]
    assert "22" in catalog["target_versions"]
    assert "20" not in catalog["target_versions"]

    # Test with default today (today=None)
    catalog_default_today = resolve_catalog(
        platforms=["linux-x64"],
        latest_lts=True,
    )
    assert isinstance(catalog_default_today["releases"], list)


@respx.mock
def test_resolve_catalog_platform_aliases():
    mock_index: NodeIndex = [
        {"version": "v22.14.0", "files": ["osx-arm64-tar"]},
        {"version": "v18.20.0", "files": ["win-x64-zip"]},
    ]
    raw_tab = "version\tdate\nv22.14.0\t2025-02-18\nv18.20.0\t2024-03-26\n"

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )

    # darwin-arm64 matches osx-arm64-tar
    darwin_catalog = resolve_catalog(
        versions=["22"],
        platforms=["darwin-arm64"],
    )
    assert len(darwin_catalog["releases"]) == 1
    assert darwin_catalog["releases"][0]["version"] == "v22.14.0"

    # osx-arm64 alias matches osx-arm64-tar
    alias_catalog = resolve_catalog(
        versions=["22"],
        platforms=["osx-arm64"],
    )
    assert len(alias_catalog["releases"]) == 1
    assert alias_catalog["releases"][0]["version"] == "v22.14.0"

    # win-x64 matches win-x64-zip
    win_catalog = resolve_catalog(
        versions=["18"],
        platforms=["win-x64"],
    )
    assert len(win_catalog["releases"]) == 1
    assert win_catalog["releases"][0]["version"] == "v18.20.0"


@respx.mock
def test_resolve_catalog_custom_urls_and_empty():
    custom_dist = "https://custom.internal/dist"
    custom_schedule = "https://custom.internal/schedule.json"

    respx.get(f"{custom_dist}/index.json").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{custom_dist}/index.tab").mock(
        return_value=httpx.Response(200, text="version\tdate\n")
    )

    catalog = resolve_catalog(
        nodejs_dist_url=custom_dist,
        schedule_url=custom_schedule,
    )
    assert catalog["releases"] == []
    assert catalog["index_tab_content"] == "version\tdate\n"
    assert catalog["target_versions"] == []


@respx.mock
def test_resolve_catalog_http_error():
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(404)
    )

    with pytest.raises(httpx.HTTPStatusError):
        resolve_catalog(versions=["22"])


@respx.mock
def test_resolve_catalog_all_versions_with_empty_and_blank_tab_lines():
    mock_index: NodeIndex = [
        {"version": "v22.14.0", "files": ["linux-x64"]},
        {"version": ""},
    ]
    raw_tab = "version\tdate\n\nv22.14.0\t2025-02-18\n\n"

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )

    catalog = resolve_catalog()
    assert len(catalog["releases"]) == 1
    assert catalog["releases"][0]["version"] == "v22.14.0"
    assert "v22.14.0\t" in catalog["index_tab_content"]


@respx.mock
def test_resolve_catalog_multiple_exact_versions_in_same_major():
    mock_index: NodeIndex = [
        {"version": "v20.18.1", "files": ["linux-x64"]},
        {"version": "v20.11.1", "files": ["linux-x64"]},
        {"version": "v20.9.0", "files": ["linux-x64"]},
    ]
    raw_tab = "version\tdate\nv20.18.1\t2024-11-20\nv20.11.1\t2024-02-14\nv20.9.0\t2023-10-24\n"

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )

    catalog = resolve_catalog(
        versions=["20.11.1", "20.18.1"],
        platforms=["linux-x64"],
    )

    versions = [r["version"] for r in catalog["releases"]]
    assert versions == ["v20.18.1", "v20.11.1"]


@respx.mock
def test_resolve_catalog_platform_fallback_to_earlier_patch():
    # v22.15.0 exists upstream but only for Windows, v22.14.1 is available for linux-x64
    mock_index: NodeIndex = [
        {"version": "v22.15.0", "files": ["win-x64-zip"]},
        {"version": "v22.14.1", "files": ["linux-x64", "win-x64-zip"]},
    ]
    raw_tab = "version\tdate\nv22.15.0\t2025-03-01\nv22.14.1\t2025-02-18\n"

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )

    catalog = resolve_catalog(
        versions=["22"],
        platforms=["linux-x64"],
    )

    assert len(catalog["releases"]) == 1
    assert catalog["releases"][0]["version"] == "v22.14.1"


@respx.mock
def test_resolve_catalog_multi_platforms_any_match():
    # Releases where some versions only support one of the requested platforms
    mock_index: NodeIndex = [
        {"version": "v22.14.1", "files": ["linux-x64"]},
        {"version": "v22.14.0", "files": ["osx-arm64-tar"]},
        {"version": "v20.18.1", "files": ["linux-x64"]},
    ]
    raw_tab = "version\tdate\nv22.14.1\t2025-02-18\nv20.18.1\t2024-11-20\n"

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )

    catalog = resolve_catalog(
        versions=["22", "20"],
        platforms=["linux-x64", "darwin-arm64"],
    )

    versions = [r["version"] for r in catalog["releases"]]
    assert "v22.14.1" in versions
    assert "v20.18.1" in versions


@respx.mock
def test_resolve_catalog_null_files_and_int_versions():
    mock_index: NodeIndex = [
        {"version": "v22.14.0", "files": None},  # explicit None files
        {"version": "v20.18.1", "files": ["linux-x64"]},
    ]
    raw_tab = "version\tdate\nv20.18.1\t2024-11-20\n"

    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_index)
    )
    respx.get(f"{DEFAULT_NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=raw_tab)
    )

    catalog = resolve_catalog(
        versions=[20],
        platforms=["linux-x64"],
    )

    assert len(catalog["releases"]) == 1
    assert catalog["releases"][0]["version"] == "v20.18.1"
    assert catalog["target_versions"] == ["20"]
