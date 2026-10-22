from __future__ import annotations

import httpx
import respx
from node_oasis.metadata import (
    NODEJS_DIST_URL,
    SCHEDULE_URL,
    fetch_index_json,
    fetch_index_tab,
    fetch_schedule,
)


@respx.mock
def test_fetch_index_json():
    mock_data = [{"version": "v22.14.0", "lts": "Jod", "files": ["linux-x64"]}]
    route = respx.get(f"{NODEJS_DIST_URL}/index.json").mock(
        return_value=httpx.Response(200, json=mock_data)
    )

    result = fetch_index_json()

    assert result == mock_data
    assert route.called


@respx.mock
def test_fetch_index_json_custom_url():
    custom_url = "https://custom.mirror/index.json"
    route = respx.get(custom_url).mock(return_value=httpx.Response(200, json=[]))

    result = fetch_index_json(url=custom_url, timeout=15.0)

    assert result == []
    assert route.called


@respx.mock
def test_fetch_index_tab():
    mock_tab = "version\tdate\tv22.14.0\t2025-02-18\n"
    route = respx.get(f"{NODEJS_DIST_URL}/index.tab").mock(
        return_value=httpx.Response(200, text=mock_tab)
    )

    result = fetch_index_tab()

    assert result == mock_tab
    assert route.called


@respx.mock
def test_fetch_index_tab_custom_url():
    custom_url = "https://custom.mirror/index.tab"
    route = respx.get(custom_url).mock(
        return_value=httpx.Response(200, text="header\n")
    )

    result = fetch_index_tab(url=custom_url)

    assert result == "header\n"
    assert route.called


@respx.mock
def test_fetch_schedule():
    mock_schedule = {"v22": {"end": "2027-04-30", "lts": "2024-10-29"}}
    route = respx.get(SCHEDULE_URL).mock(
        return_value=httpx.Response(200, json=mock_schedule)
    )

    result = fetch_schedule()

    assert result == mock_schedule
    assert route.called


@respx.mock
def test_fetch_schedule_custom_url():
    custom_url = "https://custom.org/schedule.json"
    route = respx.get(custom_url).mock(return_value=httpx.Response(200, json={}))

    result = fetch_schedule(url=custom_url)

    assert result == {}
    assert route.called
