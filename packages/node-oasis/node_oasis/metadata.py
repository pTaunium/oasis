"""Fetch upstream Node.js distribution metadata."""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import NodeIndex, ReleaseSchedule

NODEJS_DIST_URL = "https://nodejs.org/dist"
SCHEDULE_URL = "https://raw.githubusercontent.com/nodejs/Release/main/schedule.json"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def fetch_index_json(
    *, url: str = f"{NODEJS_DIST_URL}/index.json", timeout: float = 30.0
) -> NodeIndex:
    """Download and return index.json as a list of releases."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def fetch_index_tab(
    *, url: str = f"{NODEJS_DIST_URL}/index.tab", timeout: float = 30.0
) -> str:
    """Download and return index.tab as raw text."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def fetch_schedule(
    *, url: str = SCHEDULE_URL, timeout: float = 30.0
) -> ReleaseSchedule:
    """Download and return schedule.json mapping version to schedule."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()
