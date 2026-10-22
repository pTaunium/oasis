"""Shared data models for node-oasis."""

from __future__ import annotations

from typing import TypedDict


class ChecksumMismatchError(Exception):
    """Raised when checksum verification fails."""


class NodeRelease(TypedDict, total=False):
    """A single entry from nodejs.org/dist/index.json."""

    version: str  # e.g. "v22.14.0"
    date: str  # e.g. "2024-10-29"
    files: list[str] | None  # e.g. ["linux-x64", "headers", ...]
    npm: str
    v8: str
    uv: str
    zlib: str
    openssl: str
    modules: str
    lts: str | bool  # False or codename string like "Jod"
    security: bool


# The full index is a list of NodeRelease entries
type NodeIndex = list[NodeRelease]


# schedule.json maps version keys like "v20" to schedule info
class ScheduleEntry(TypedDict, total=False):
    start: str
    lts: str
    maintenance: str
    end: str
    codename: str


type ReleaseSchedule = dict[str, ScheduleEntry]


class ResolvedCatalog(TypedDict):
    """Manifest returned by Release Catalog containing resolved releases and index metadata."""

    releases: list[NodeRelease]
    index_tab_content: str
    target_versions: list[str]


class UpstreamConfig(TypedDict, total=False):
    nodejs_dist_url: str
    schedule_url: str
    platform: str
    platforms: list[str]


class ToolsConfig(TypedDict, total=False):
    nvm_api_url: str
    fnm_api_url: str
    nvm_sha256: str
    fnm_sha256: dict[str, str]


class AppConfig(TypedDict, total=False):
    upstream: UpstreamConfig
    tools: ToolsConfig


class NvmReleaseInfo(TypedDict, total=False):
    version: str
    tarball_filename: str


class FnmReleaseInfo(TypedDict, total=False):
    version: str
    zip_filename: str
    zip_filenames: list[str]
