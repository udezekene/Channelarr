"""Channelarr CLI argument parser.

All flags are per-run overrides only — none of them persist to config.yaml.
"""

from __future__ import annotations
import argparse
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="channelarr",
        description=(
            "Safety-first Dispatcharr channel and stream manager. "
            "Dry-run by default — pass --apply to commit changes."
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the planned changes (default: dry-run, shows diff only)",
    )
    parser.add_argument(
        "--allow-new-channels",
        action="store_true",
        dest="allow_new_channels",
        help="Permit channel creation this run (overrides config default)",
    )
    parser.add_argument(
        "--allow-delete",
        action="store_true",
        dest="allow_delete",
        help="Permit channel deletion this run (overrides config default)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="Path to config.yaml (default: ~/.config/channelarr/config.yaml)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Trigger an M3U refresh before fetching streams",
    )
    parser.add_argument(
        "--reconfigure",
        action="store_true",
        help="Re-run the setup wizard and overwrite the existing config",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Step through each proposed change for per-change approval",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all match candidates and scores for each channel",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the final summary line (N updated, N created, N skipped)",
    )
    parser.add_argument(
        "--strategy",
        choices=["regex", "exact", "fuzzy"],
        metavar="NAME",
        help="Override matching strategy for this run (regex | exact | fuzzy)",
    )
    parser.add_argument(
        "--dedup",
        action="store_true",
        help=(
            "Find duplicate channels (same normalized name) and merge their streams. "
            "Shows a dry-run diff by default; add --apply to commit."
        ),
    )
    parser.add_argument(
        "--pair",
        action="store_true",
        help=(
            "Run the pairing wizard after the diff — resolve ambiguous matches and "
            "approve locked channel changes. Selections are saved to the pairing store."
        ),
    )
    parser.add_argument(
        "--unlock",
        action="append",
        dest="unlock",
        metavar="CHANNEL",
        default=[],
        help=(
            "Unlock a locked channel for this run only (not persisted). "
            "Repeat to unlock multiple: --unlock 'BBC One' --unlock 'CNN'"
        ),
    )

    return parser.parse_args(argv)
