#!/usr/bin/env python3
"""Build script for uv-oasis.

Downloads selected Python standalone builds and generates a JSON index
for use with ``UV_PYTHON_DOWNLOADS_JSON_URL``.

Usage::

    uv run python build.py --output ./dist
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from uv_oasis.catalog import resolve_catalog
from uv_oasis.config import load_filter_config
from uv_oasis.downloader import download_tarballs
from uv_oasis.index_generator import write_json_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download Python standalone builds and generate index."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist"),
        help="Output directory (default: ./dist)",
    )
    parser.add_argument(
        "--metadata-url",
        default=None,
        help="Override the download-metadata.json URL",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.toml",
        help="Path to the TOML configuration file (default: config.toml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without downloading",
    )
    args = parser.parse_args(argv)

    output_dir: Path = args.output
    assets_dir = output_dir / "assets"
    index_path = output_dir / "download-metadata.json.template"

    # Step 1 & 2: Resolve catalog
    filter_config = load_filter_config(args.config)
    catalog = resolve_catalog(filter_config, metadata_url=args.metadata_url)
    entries = catalog["entries"]
    logger.info("Filtered to %d entries:", len(entries))
    for dist_id in entries:
        entry = entries[dist_id]
        size_info = ""
        variant = entry.get("variant") or "normal"
        logger.info("  %s (variant=%s)%s", dist_id, variant, size_info)

    if args.dry_run:
        logger.info("Dry run — skipping downloads")
        return 0

    # Step 3: Download
    logger.info("Downloading tarballs to %s...", assets_dir)
    download_tarballs(entries, assets_dir)

    # Step 4: Generate index
    logger.info("Generating JSON index...")
    write_json_index(entries, index_path)

    logger.info("Done! Output directory: %s", output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
