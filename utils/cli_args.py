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
        "--cleanup",
        action="store_true",
        help=(
            "Clean up channels within each group: merge duplicates then rename "
            "prefixed names (e.g. 'UK-CNN' → 'CNN'). Dry-run by default; "
            "add --apply to commit."
        ),
    )
    parser.add_argument(
        "--rename-only",
        action="store_true",
        dest="rename_only",
        help="With --cleanup: skip duplicate merging, rename channels only.",
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
        "--debug-channel",
        type=str,
        dest="debug_channel",
        metavar="NAME",
        help="Show stream sort keys for a channel (case-insensitive substring match). Requires provider_priority to be set.",
    )
    parser.add_argument(
        "--inspect-channel",
        type=str,
        dest="inspect_channel",
        metavar="NAME",
        help=(
            "Dump the raw API response for a channel matching NAME (case-insensitive substring) and exit. "
            "Use this to see exactly how Dispatcharr stores the streams field."
        ),
    )
    parser.add_argument(
        "--inspect-streams",
        action="store_true",
        dest="inspect_streams",
        help=(
            "Dump the raw API response for a sample of streams and exit. "
            "Use this to discover what metadata Dispatcharr stores per stream."
        ),
    )
    parser.add_argument(
        "--inspect-count",
        type=int,
        default=3,
        dest="inspect_count",
        metavar="N",
        help="Number of streams to inspect (default: 3). Used with --inspect-streams.",
    )
    parser.add_argument(
        "--epg-min-confidence",
        type=float,
        default=None,
        dest="epg_min_confidence",
        metavar="FLOAT",
        help=(
            "Only show/apply EPG proposals at or above this confidence (0.0–1.0). "
            "Overrides epg_min_confidence in config.yaml for this run. "
            "Example: --epg-min-confidence 0.8"
        ),
    )
    parser.add_argument(
        "--assign-epg",
        action="store_true",
        dest="assign_epg",
        help=(
            "Propose EPG assignments for channels that have none. "
            "Uses the channel's primary stream provider and group suffix pattern "
            "to find the best match in Dispatcharr's EPG data. "
            "Dry-run by default; add --apply to commit."
        ),
    )
    parser.add_argument(
        "--inspect-epg",
        action="store_true",
        dest="inspect_epg",
        help="Probe Dispatcharr's EPG API and dump a sample of EPG channel entries.",
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
    parser.add_argument(
        "--audit",
        action="store_true",
        help=(
            "Scan your library for health issues: channels without EPG, "
            "channels without streams, orphan streams, and stale EPG references. "
            "Read-only. Respects --group / --group-id."
        ),
    )
    parser.add_argument(
        "--group",
        type=str,
        metavar="NAME",
        help=(
            "Scope this run to a single channel group by name "
            "(e.g. --group 'Sports'). Works with --cleanup, --assign-epg, "
            "and the main pipeline."
        ),
    )
    parser.add_argument(
        "--group-id",
        type=int,
        dest="group_id",
        metavar="ID",
        help="Scope this run to a single channel group by numeric ID.",
    )

    return parser.parse_args(argv)
