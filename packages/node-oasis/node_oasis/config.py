"""Configuration loading and validation for node-oasis."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from .models import AppConfig, ToolsConfig

logger = logging.getLogger(__name__)

DEFAULT_NODEJS_DIST_URL = "https://nodejs.org/dist"
DEFAULT_SCHEDULE_URL = (
    "https://raw.githubusercontent.com/nodejs/Release/main/schedule.json"
)
DEFAULT_NVM_API_URL = "https://api.github.com/repos/nvm-sh/nvm/releases/latest"
DEFAULT_FNM_API_URL = "https://api.github.com/repos/Schniz/fnm/releases/latest"
DEFAULT_PLATFORM = "linux-x64"
DEFAULT_PLATFORMS = ["linux-x64"]


def load_config(config_path: Path) -> AppConfig:
    """Load configuration from a TOML file with sensible defaults."""
    if not config_path.is_file():
        logger.warning("Config file %s not found. Using defaults.", config_path)
        return {
            "upstream": {
                "nodejs_dist_url": DEFAULT_NODEJS_DIST_URL,
                "schedule_url": DEFAULT_SCHEDULE_URL,
                "platform": DEFAULT_PLATFORM,
                "platforms": DEFAULT_PLATFORMS,
            },
            "tools": {
                "nvm_api_url": DEFAULT_NVM_API_URL,
                "fnm_api_url": DEFAULT_FNM_API_URL,
            },
        }

    with config_path.open("rb") as f:
        raw_config = tomllib.load(f)

    raw_upstream = raw_config.get("upstream", {})
    raw_tools = raw_config.get("tools", {})

    platforms: list[str]
    if "platforms" in raw_upstream:
        platforms = list(raw_upstream["platforms"])
    elif "platform" in raw_upstream:
        platforms = [raw_upstream["platform"]]
    else:
        platforms = DEFAULT_PLATFORMS

    primary_platform = platforms[0] if platforms else DEFAULT_PLATFORM

    tools_dict: ToolsConfig = {
        "nvm_api_url": raw_tools.get("nvm_api_url", DEFAULT_NVM_API_URL),
        "fnm_api_url": raw_tools.get("fnm_api_url", DEFAULT_FNM_API_URL),
    }
    if "nvm_sha256" in raw_tools:
        tools_dict["nvm_sha256"] = raw_tools["nvm_sha256"]
    if "fnm_sha256" in raw_tools:
        tools_dict["fnm_sha256"] = raw_tools["fnm_sha256"]

    nodejs_dist_url = str(
        raw_upstream.get("nodejs_dist_url", DEFAULT_NODEJS_DIST_URL)
    ).rstrip("/")

    return {
        "upstream": {
            "nodejs_dist_url": nodejs_dist_url,
            "schedule_url": raw_upstream.get("schedule_url", DEFAULT_SCHEDULE_URL),
            "platform": primary_platform,
            "platforms": platforms,
        },
        "tools": tools_dict,
    }
