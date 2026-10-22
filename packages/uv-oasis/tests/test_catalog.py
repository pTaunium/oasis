from __future__ import annotations

import httpx
import pytest
import respx
from uv_oasis.catalog import (
    DOWNLOAD_METADATA_URL,
    _extract_version_tuple,
    _is_stable,
    resolve_catalog,
)
from uv_oasis.models import FilterConfig, MetadataIndex, PlatformSpec


def test_is_stable():
    assert _is_stable({"prerelease": ""}) is True
    assert _is_stable({"prerelease": "b1"}) is False
    assert _is_stable({}) is True  # missing prerelease defaults to ""


def test_extract_version_tuple():
    assert _extract_version_tuple({"major": 3, "minor": 12, "patch": 1}) == (3, 12, 1)


@respx.mock
def test_resolve_catalog_filtering_and_sorting():
    metadata: MetadataIndex = {
        "cpython-3.12.0-linux-gnu": {
            "name": "cpython",
            "major": 3,
            "minor": 12,
            "patch": 0,
            "prerelease": "",
            "variant": None,
            "os": "linux",
            "arch": {"family": "x86_64", "variant": None},
            "libc": "gnu",
            "url": "https://example.com/3.12.0.tar.gz",
        },
        "cpython-3.12.1-linux-gnu": {
            "name": "cpython",
            "major": 3,
            "minor": 12,
            "patch": 1,
            "prerelease": "",
            "variant": None,
            "os": "linux",
            "arch": {"family": "x86_64", "variant": None},
            "libc": "gnu",
            "url": "https://example.com/3.12.1.tar.gz",
        },
        "cpython-3.10.0-linux-gnu": {
            "name": "cpython",
            "major": 3,
            "minor": 10,
            "patch": 0,
            "prerelease": "",
            "variant": None,
            "os": "linux",
            "arch": {"family": "x86_64", "variant": None},
            "libc": "gnu",
            "url": "https://example.com/3.10.0.tar.gz",
        },
        "pypy-3.12": {
            "name": "pypy",  # Should be ignored (not cpython)
        },
        "cpython-3.13.0b1": {
            "name": "cpython",
            "prerelease": "b1",  # Should be ignored (not stable)
        },
        "cpython-3.12.1-freethreaded": {
            "name": "cpython",
            "prerelease": "",
            "variant": "freethreaded",  # Should be ignored (not in python_variants)
        },
        "cpython-3.12.1-mac": {
            "name": "cpython",
            "prerelease": "",
            "variant": None,
            "os": "darwin",  # Should be ignored (not in platforms)
            "arch": {"family": "aarch64", "variant": None},
            "libc": "none",
        },
    }

    respx.get(DOWNLOAD_METADATA_URL).mock(
        return_value=httpx.Response(200, json=metadata)
    )

    config = FilterConfig(
        python_variants={None},
        cpu_variants={None},
        platforms=[PlatformSpec("linux", "x86_64", "gnu")],
    )

    catalog = resolve_catalog(config)
    entries = catalog["entries"]

    assert len(entries) == 2
    # Verify latest patch kept (3.12.1 over 3.12.0) and sorted descending (3.12 then 3.10)
    keys = list(entries.keys())
    assert keys == ["cpython-3.12.1-linux-gnu", "cpython-3.10.0-linux-gnu"]


@respx.mock
def test_resolve_catalog_custom_url():
    custom_url = "https://custom.test/meta.json"
    respx.get(custom_url).mock(return_value=httpx.Response(200, json={}))

    config = FilterConfig(
        python_variants={None},
        cpu_variants={None},
        platforms=[PlatformSpec("linux", "x86_64", "gnu")],
    )

    catalog = resolve_catalog(config, metadata_url=custom_url, timeout=15.0)
    assert catalog["entries"] == {}


@respx.mock
def test_resolve_catalog_http_error():
    respx.get(DOWNLOAD_METADATA_URL).mock(return_value=httpx.Response(404))

    config = FilterConfig(
        python_variants={None},
        cpu_variants={None},
        platforms=[],
    )

    with pytest.raises(httpx.HTTPStatusError):
        resolve_catalog(config)
