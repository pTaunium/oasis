"""Shared data models for uv-oasis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


class ArchEntry(TypedDict):
    family: str
    variant: str | None


class MetadataEntry(TypedDict, total=False):
    name: Literal["cpython", "pypy"]
    arch: ArchEntry
    os: Literal["linux", "windows", "darwin"]
    libc: str | None
    major: int
    minor: int
    patch: int
    prerelease: str
    url: str
    sha256: str | None
    variant: Literal["freethreaded"] | None


type MetadataIndex = dict[str, MetadataEntry]


class ResolvedCatalog(TypedDict):
    """Manifest returned by Release Catalog containing resolved python distributions."""

    entries: MetadataIndex


@dataclass(frozen=True)
class PlatformSpec:
    """A target platform specification for filtering."""

    os: str
    arch_family: str
    libc: str | None = None  # None for Windows

    def matches(
        self,
        entry: MetadataEntry,
        allowed_cpu_variants: set[str | None],
    ) -> bool:
        if entry.get("os") != self.os:
            return False
        arch = entry.get("arch", {})
        if arch.get("family") != self.arch_family:
            return False
        if arch.get("variant") not in allowed_cpu_variants:
            return False
        return not (self.libc is not None and entry.get("libc") != self.libc)


@dataclass(frozen=True)
class FilterConfig:
    """Holds configuration for filtering metadata entries."""

    python_variants: set[str | None]
    cpu_variants: set[str | None]
    platforms: list[PlatformSpec]
