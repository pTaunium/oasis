#!/usr/bin/env python3
"""Build script for node-oasis.

Downloads selected Node.js binaries and generates index.json and index.tab.

Usage::

    python build.py --latest-lts --output ./dist
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from node_oasis.catalog import resolve_catalog
from node_oasis.config import load_config
from node_oasis.downloader import download_node_releases
from node_oasis.index_generator import write_index_json, write_index_tab
from node_oasis.tools import download_tools
from node_oasis.utils import normalize_platform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Main orchestrator function."""
    parser = argparse.ArgumentParser(
        description="Download Node.js releases and generate index files."
    )
    parser.add_argument(
        "--versions",
        nargs="+",
        type=str,
        help="Major version numbers or exact versions to include (e.g., 20 22.14.0)",
    )
    parser.add_argument(
        "--latest-lts",
        action="store_true",
        help="Auto-select all Active + Maintenance LTS versions",
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        type=str,
        default=None,
        help="Target platforms (e.g., linux-x64 darwin-arm64)",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("dist"),
        help="Output directory (default: ./dist)",
    )
    parser.add_argument(
        "--tools",
        nargs="*",
        choices=["nvm", "fnm"],
        default=None,
        help="Tools to download (e.g., --tools nvm fnm)",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Don't download any tools",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.toml",
        help="Path to config.toml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded",
    )

    args = parser.parse_args(argv)

    if not args.versions and not args.latest_lts:
        parser.error("At least one of --versions or --latest-lts must be specified")

    if args.tools is not None and args.no_tools:
        parser.error("--tools and --no-tools are mutually exclusive")

    tools_to_download = (
        []
        if args.no_tools
        else (args.tools if args.tools is not None else ["nvm", "fnm"])
    )

    config = load_config(args.config)
    upstream = config.get("upstream", {})
    tools_config = config.get("tools", {})

    nodejs_dist_url = upstream.get("nodejs_dist_url", "https://nodejs.org/dist").rstrip(
        "/"
    )
    schedule_url = upstream.get(
        "schedule_url",
        "https://raw.githubusercontent.com/nodejs/Release/main/schedule.json",
    )

    raw_platforms = (
        args.platforms
        or ([args.platform] if args.platform else None)
        or upstream.get("platforms")
        or [upstream.get("platform", "linux-x64")]
    )
    platforms = [normalize_platform(p) for p in raw_platforms]

    catalog = resolve_catalog(
        versions=args.versions,
        platforms=platforms,
        latest_lts=args.latest_lts,
        nodejs_dist_url=nodejs_dist_url,
        schedule_url=schedule_url,
    )
    filtered_releases = catalog["releases"]
    index_tab_content = catalog["index_tab_content"]
    target_versions = catalog["target_versions"]

    if not filtered_releases:
        logger.error("No Node.js releases matched target versions: %s", target_versions)
        return 1

    if args.dry_run:
        platforms_str = ", ".join(platforms)
        print(f"\n=== Node.js Versions (platforms: {platforms_str}) ===")
        for r in filtered_releases:
            lts_str = f"(LTS: {r['lts']})" if r.get("lts") else ""
            print(f"  {r['version']:<10} {lts_str}")

        print("\n=== Tools ===")
        for t in tools_to_download:
            print(f"  {t}: latest")
        return 0

    dist_dir = args.output / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    tools_dir = args.output / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading Node.js releases...")
    download_node_releases(
        filtered_releases,
        dist_dir,
        platforms=platforms,
        dist_url=nodejs_dist_url,
    )

    logger.info("Writing index files...")
    write_index_json(filtered_releases, dist_dir / "index.json")
    write_index_tab(index_tab_content, dist_dir / "index.tab")

    if tools_to_download:
        logger.info("Downloading tools...")
        nvm_url = tools_config.get("nvm_api_url")
        fnm_url = tools_config.get("fnm_api_url")
        download_tools(
            tools_dir,
            tools=tools_to_download,
            platforms=platforms,
            **({"nvm_api_url": nvm_url} if nvm_url else {}),
            **({"fnm_api_url": fnm_url} if fnm_url else {}),
            **(
                {"nvm_sha256": tools_config.get("nvm_sha256")}
                if tools_config.get("nvm_sha256")
                else {}
            ),
            **(
                {"fnm_sha256": tools_config.get("fnm_sha256")}
                if tools_config.get("fnm_sha256")
                else {}
            ),
        )

    logger.info("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
